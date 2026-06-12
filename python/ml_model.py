import os
import sys
import torch
import torch.nn as nn
from torch.utils.data import Dataset
import numpy as np
import math
from datetime import datetime

# Include current directory in system path to import database utilities
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_conn

class GlobalInventoryDataset(Dataset):
    """
    A PyTorch Dataset that loads historical inventory sessions and feedback logs 
    to generate sequence data for training the intelligent tracking model.

    Attributes:
        seq_len (int): The fixed length of historical sessions to use for each prediction sequence.
        samples (list): A curated list of training samples containing features, tags, and labels.
        tag_to_id (dict): A mapping from literal RFID tag strings to integer indices for embeddings.
    """
    def __init__(self, seq_len=50):
        self.seq_len = seq_len
        self.samples = []
        self.tag_to_id = {}
        
        self.load_data()

    def _get_tag_id(self, tag: str) -> int:
        """
        Convert a raw RFID tag string into a unique integer index for the embedding layer.

        Args:
            tag (str): The original RFID tag identifier.

        Returns:
            int: The corresponding unique integer index.
        """
        if tag not in self.tag_to_id:
            self.tag_to_id[tag] = len(self.tag_to_id)
        return self.tag_to_id[tag]

    def load_data(self):
        """
        Extract sessions and feedback logs from the SQLite database, align them chronologically,
        and build padded feature sequences and labels for GRU model training.
        """
        conn = get_conn()
        cur = conn.cursor()

        # Load all completed sessions in chronological order
        cur.execute("SELECT rfid_tag_id, taken_at, session_duration_s FROM sessions ORDER BY taken_at ASC")
        sessions = cur.fetchall()

        # Load all manual feedback logs in chronological order
        cur.execute("SELECT rfid_tag_id, quantity_level, timestamp FROM feedback_logs ORDER BY timestamp ASC")
        feedbacks = cur.fetchall()
        conn.close()

        # Phase 1: Parse sessions into structured features
        parsed_sessions = []
        for s in sessions:
            if s["session_duration_s"] is None:
                continue
            dt = datetime.fromisoformat(s["taken_at"])
            tag_idx = self._get_tag_id(s["rfid_tag_id"])
            
            # Normalize duration to a maximum of 5 hours
            dur = min(s["session_duration_s"] / 3600.0, 5.0) 
            
            # Extract cyclical time-of-day features (sin/cos encoding)
            hour = dt.hour + dt.minute / 60.0
            hour_sin = math.sin(2 * math.pi * hour / 24.0)
            hour_cos = math.cos(2 * math.pi * hour / 24.0)
            
            parsed_sessions.append({
                "ts": dt,
                "tag_idx": tag_idx,
                "features": [dur, hour_sin, hour_cos]
            })

        # Define the numerical mapping for classification labels
        label_map = {"LITTLE": 0, "MEDIUM": 1, "A LOT": 2}

        # Phase 2: For each feedback log, gather the preceding `seq_len` sessions to form a sample
        session_idx = 0
        for fb in feedbacks:
            fb_dt = datetime.fromisoformat(fb["timestamp"])
            label = label_map.get(fb["quantity_level"])
            if label is None:
                continue

            target_tag_idx = self._get_tag_id(fb["rfid_tag_id"])

            # Advance the session pointer to just before the feedback timestamp
            while session_idx < len(parsed_sessions) and parsed_sessions[session_idx]["ts"] < fb_dt:
                session_idx += 1

            # Extract the historical window of sessions
            start_idx = max(0, session_idx - self.seq_len)
            seq = parsed_sessions[start_idx:session_idx]
            
            if len(seq) == 0:
                # Discard feedbacks lacking any historical context
                continue 
            
            # Initialize empty lists for features and tags
            seq_features = []
            seq_tags = []
            
            # Pre-pad the sequence with zeros if shorter than seq_len
            pad_len = self.seq_len - len(seq)
            for _ in range(pad_len):
                seq_features.append([0.0, 0.0, 0.0])
                seq_tags.append(0) # Pad token (assumes 0 is safe/neutral for embedding)
                
            for s in seq:
                seq_features.append(s["features"])
                seq_tags.append(s["tag_idx"])

            # Append the fully constructed tensor dictionary to the dataset
            self.samples.append({
                "features": torch.tensor(seq_features, dtype=torch.float32),
                "tags": torch.tensor(seq_tags, dtype=torch.long),
                "target_tag": torch.tensor(target_tag_idx, dtype=torch.long),
                "label": torch.tensor(label, dtype=torch.long)
            })

    def __len__(self) -> int:
        """Return the total number of samples in the dataset."""
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        """Retrieve a specific sample by its index."""
        return self.samples[idx]

    def get_num_tags(self) -> int:
        """
        Calculate the total vocabulary size for the tag embedding layer.

        Returns:
            int: The maximum integer tag ID plus one.
        """
        return max(list(self.tag_to_id.values()) + [0]) + 1


class GlobalQuantityGRU(nn.Module):
    """
    A Recurrent Neural Network (GRU) designed to predict residual chemical 
    quantities based on temporal usage sequences across all laboratory substances.

    Args:
        num_tags (int): The total number of unique RFID tags in the system vocabulary.
        embed_size (int, optional): The dimensionality of the tag embeddings. Defaults to 8.
        hidden_size (int, optional): The hidden state size of the GRU layer. Defaults to 32.
    """
    def __init__(self, num_tags: int, embed_size: int = 8, hidden_size: int = 32):
        super(GlobalQuantityGRU, self).__init__()
        
        self.tag_embedding = nn.Embedding(num_tags, embed_size)
        
        # GRU input consists of 3 temporal features [duration, hour_sin, hour_cos] plus the tag embedding
        rnn_input_size = 3 + embed_size
        self.gru = nn.GRU(input_size=rnn_input_size, hidden_size=hidden_size, batch_first=True)
        
        # Fully connected network mapping the final GRU state and target embedding to 3 quantity classes
        self.fc = nn.Sequential(
            nn.Linear(hidden_size + embed_size, 16),
            nn.ReLU(),
            nn.Linear(16, 3) # Output classes: [LITTLE, MEDIUM, A LOT]
        )

    def forward(self, features: torch.Tensor, tags: torch.Tensor, target_tag: torch.Tensor) -> torch.Tensor:
        """
        Perform a forward pass through the network.

        Args:
            features (torch.Tensor): A tensor of shape (batch, seq_len, 3) containing temporal features.
            tags (torch.Tensor): A tensor of shape (batch, seq_len) containing historical tag indices.
            target_tag (torch.Tensor): A tensor of shape (batch,) containing the index of the queried tag.

        Returns:
            torch.Tensor: Logits tensor of shape (batch, 3) representing class probabilities.
        """
        # 1. Generate embeddings for the historical sequence tags
        tag_emb = self.tag_embedding(tags) # Shape: (batch, seq_len, embed_size)
        
        # 2. Concatenate raw temporal features with the learned embeddings
        x = torch.cat([features, tag_emb], dim=-1) # Shape: (batch, seq_len, 3 + embed_size)
        
        # 3. Process the sequence through the GRU
        _, h_n = self.gru(x) # h_n is the final hidden state, Shape: (1, batch, hidden_size)
        h_n = h_n.squeeze(0) # Shape: (batch, hidden_size)
        
        # 4. Generate an embedding for the specific target tag being queried
        target_emb = self.tag_embedding(target_tag) # Shape: (batch, embed_size)
        
        # 5. Concatenate the sequence context (h_n) with the target context (target_emb)
        out = torch.cat([h_n, target_emb], dim=-1) # Shape: (batch, hidden_size + embed_size)
        
        # 6. Compute the final classification logits
        logits = self.fc(out) # Shape: (batch, 3)
        
        return logits
