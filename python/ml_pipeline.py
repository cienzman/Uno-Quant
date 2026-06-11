import os
import sys
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from datetime import datetime
import math

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ml_model import GlobalInventoryDataset, GlobalQuantityGRU
from db_utils import get_conn

MODEL_PATH = os.path.join(os.path.dirname(__file__), "inventory_gru.pth")

# Maintain a global cache of the model for fast inference
_cached_model = None
_tag_to_id = None
_label_map_inv = {0: "LITTLE", 1: "MEDIUM", 2: "A LOT"}

def train_model(epochs=20, batch_size=32, lr=0.005):
    """
    Trains the global sequence GRU model on historical feedback logs.
    Saves the weights to inventory_gru.pth.
    """
    print("Starting ML Model training...")
    dataset = GlobalInventoryDataset(seq_len=50)
    
    if len(dataset) == 0:
        print("No training data available.")
        return

    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    num_tags = dataset.get_num_tags()
    model = GlobalQuantityGRU(num_tags=num_tags)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    
    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for batch in dataloader:
            optimizer.zero_grad()
            
            logits = model(batch["features"], batch["tags"], batch["target_tag"])
            loss = criterion(logits, batch["label"])
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
        print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss / len(dataloader):.4f}")

    # Save model and mapping
    torch.save({
        'model_state_dict': model.state_dict(),
        'tag_to_id': dataset.tag_to_id,
        'num_tags': num_tags
    }, MODEL_PATH)
    
    # Invalidate cache
    global _cached_model
    _cached_model = None
    
    print(f"Model saved to {MODEL_PATH}")

def load_model():
    global _cached_model, _tag_to_id
    if _cached_model is not None:
        return _cached_model, _tag_to_id
        
    if not os.path.exists(MODEL_PATH):
        return None, None
        
    checkpoint = torch.load(MODEL_PATH, map_location=torch.device('cpu'), weights_only=False)
    
    num_tags = checkpoint.get('num_tags', 10)
    model = GlobalQuantityGRU(num_tags=num_tags)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    _cached_model = model
    _tag_to_id = checkpoint['tag_to_id']
    
    return _cached_model, _tag_to_id

def predict_quantity(rfid_tag_id: str) -> str:
    """
    Given a target rfid_tag_id, fetches the most recent global sessions
    and passes them to the GRU to predict the current quantity level.
    """
    model, tag_to_id = load_model()
    if model is None:
        print("No trained model found. Defaulting to UNKNOWN.")
        return "UNKNOWN"
        
    # Get recent sessions
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT rfid_tag_id, taken_at, session_duration_s 
        FROM sessions 
        WHERE session_duration_s IS NOT NULL
        ORDER BY taken_at DESC 
        LIMIT 50
    """)
    recent_sessions = cur.fetchall()
    conn.close()
    
    # Needs chronological order
    recent_sessions.reverse()
    
    # Pad or format
    seq_features = []
    seq_tags = []
    seq_len = 50
    
    pad_len = seq_len - len(recent_sessions)
    for _ in range(pad_len):
        seq_features.append([0.0, 0.0, 0.0])
        seq_tags.append(0)
        
    for s in recent_sessions:
        dt = datetime.fromisoformat(s["taken_at"])
        tag = s["rfid_tag_id"]
        # Use existing mapping or 0 if unknown
        tag_idx = tag_to_id.get(tag, 0)
        dur = min(s["session_duration_s"] / 3600.0, 5.0)
        hour = dt.hour + dt.minute / 60.0
        
        seq_features.append([dur, math.sin(2 * math.pi * hour / 24.0), math.cos(2 * math.pi * hour / 24.0)])
        seq_tags.append(tag_idx)
        
    target_tag_idx = tag_to_id.get(rfid_tag_id, 0)
    
    features_t = torch.tensor([seq_features], dtype=torch.float32)
    tags_t = torch.tensor([seq_tags], dtype=torch.long)
    target_t = torch.tensor([target_tag_idx], dtype=torch.long)
    
    with torch.no_grad():
        logits = model(features_t, tags_t, target_t)
        pred_idx = torch.argmax(logits, dim=-1).item()
        
    return _label_map_inv[pred_idx]

if __name__ == "__main__":
    train_model()
