import os
import sys
import torch
import torch.nn as nn
from torch.utils.data import Dataset
import numpy as np
import math
from datetime import datetime

# Import db utilities
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_conn

class GlobalInventoryDataset(Dataset):
    def __init__(self, seq_len=50):
        self.seq_len = seq_len
        self.samples = []
        self.tag_to_id = {}
        
        self.load_data()

    def _get_tag_id(self, tag):
        if tag not in self.tag_to_id:
            self.tag_to_id[tag] = len(self.tag_to_id)
        return self.tag_to_id[tag]

    def load_data(self):
        conn = get_conn()
        cur = conn.cursor()

        # Load all sessions
        cur.execute("SELECT rfid_tag_id, taken_at, session_duration_s FROM sessions ORDER BY taken_at ASC")
        sessions = cur.fetchall()

        # Load all feedback logs
        cur.execute("SELECT rfid_tag_id, quantity_level, timestamp FROM feedback_logs ORDER BY timestamp ASC")
        feedbacks = cur.fetchall()
        conn.close()

        # Build list of parsed sessions
        parsed_sessions = []
        for s in sessions:
            if s["session_duration_s"] is None:
                continue
            dt = datetime.fromisoformat(s["taken_at"])
            tag_idx = self._get_tag_id(s["rfid_tag_id"])
            dur = min(s["session_duration_s"] / 3600.0, 5.0) # max 5 hours, normalized
            hour = dt.hour + dt.minute / 60.0
            hour_sin = math.sin(2 * math.pi * hour / 24.0)
            hour_cos = math.cos(2 * math.pi * hour / 24.0)
            
            parsed_sessions.append({
                "ts": dt,
                "tag_idx": tag_idx,
                "features": [dur, hour_sin, hour_cos]
            })

        # Map labels
        label_map = {"LITTLE": 0, "MEDIUM": 1, "A LOT": 2}

        # For each feedback, gather the preceding seq_len sessions
        session_idx = 0
        for fb in feedbacks:
            fb_dt = datetime.fromisoformat(fb["timestamp"])
            label = label_map.get(fb["quantity_level"])
            if label is None:
                continue

            target_tag_idx = self._get_tag_id(fb["rfid_tag_id"])

            # Advance session_idx to just before fb_dt
            while session_idx < len(parsed_sessions) and parsed_sessions[session_idx]["ts"] < fb_dt:
                session_idx += 1

            # Get the previous seq_len sessions
            start_idx = max(0, session_idx - self.seq_len)
            seq = parsed_sessions[start_idx:session_idx]
            
            if len(seq) == 0:
                continue # No history for this feedback, skip
            
            # Pad sequence if necessary
            seq_features = []
            seq_tags = []
            
            pad_len = self.seq_len - len(seq)
            for _ in range(pad_len):
                seq_features.append([0.0, 0.0, 0.0])
                seq_tags.append(0) # pad token, though we should reserve 0 or just use 0 as arbitrary if we have embedding
                
            for s in seq:
                seq_features.append(s["features"])
                seq_tags.append(s["tag_idx"])

            self.samples.append({
                "features": torch.tensor(seq_features, dtype=torch.float32),
                "tags": torch.tensor(seq_tags, dtype=torch.long),
                "target_tag": torch.tensor(target_tag_idx, dtype=torch.long),
                "label": torch.tensor(label, dtype=torch.long)
            })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]

    def get_num_tags(self):
        # Return max id + 1
        return max(list(self.tag_to_id.values()) + [0]) + 1


class GlobalQuantityGRU(nn.Module):
    def __init__(self, num_tags, embed_size=8, hidden_size=32):
        super(GlobalQuantityGRU, self).__init__()
        
        self.tag_embedding = nn.Embedding(num_tags, embed_size)
        
        # Input to GRU: [dur, sin, cos] (3) + tag_embedding
        rnn_input_size = 3 + embed_size
        self.gru = nn.GRU(input_size=rnn_input_size, hidden_size=hidden_size, batch_first=True)
        
        # FC layer takes the final GRU hidden state + the target tag embedding
        self.fc = nn.Sequential(
            nn.Linear(hidden_size + embed_size, 16),
            nn.ReLU(),
            nn.Linear(16, 3) # 3 classes: LITTLE, MEDIUM, A LOT
        )

    def forward(self, features, tags, target_tag):
        # features: (batch, seq_len, 3)
        # tags: (batch, seq_len)
        # target_tag: (batch,)

        # 1. Embed tags
        tag_emb = self.tag_embedding(tags) # (batch, seq_len, embed_size)
        
        # 2. Concat features and embedded tags
        x = torch.cat([features, tag_emb], dim=-1) # (batch, seq_len, 3 + embed_size)
        
        # 3. Pass through GRU
        _, h_n = self.gru(x) # h_n is (1, batch, hidden_size)
        h_n = h_n.squeeze(0) # (batch, hidden_size)
        
        # 4. Embed target tag
        target_emb = self.tag_embedding(target_tag) # (batch, embed_size)
        
        # 5. Concat hidden state with target tag embedding
        out = torch.cat([h_n, target_emb], dim=-1) # (batch, hidden_size + embed_size)
        
        # 6. Final classification
        logits = self.fc(out) # (batch, 3)
        
        return logits
