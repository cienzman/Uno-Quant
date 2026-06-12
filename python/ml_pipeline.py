import os
import sys
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from datetime import datetime
import math

# Ensure local modules are accessible in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ml_model import GlobalInventoryDataset, GlobalQuantityGRU
from db_utils import get_conn

MODEL_PATH = os.path.join(os.path.dirname(__file__), "inventory_gru.pth")

# Maintain a global cache of the model weights and mappings to accelerate inference queries
_cached_model = None
_tag_to_id = None
_label_map_inv = {0: "LITTLE", 1: "MEDIUM", 2: "A LOT"}

def train_model(epochs: int = 20, batch_size: int = 32, lr: float = 0.005, patience: int = 20):
    """
    Train the global sequence GRU model using historical feedback logs.
    
    This function instantiates the dataset, splits it into training, validation, and testing sets,
    and executes a standard PyTorch training loop equipped with Early Stopping. The optimal 
    model weights are subsequently persisted to disk.

    Args:
        epochs (int, optional): The maximum number of training epochs. Defaults to 20.
        batch_size (int, optional): The number of samples per training batch. Defaults to 32.
        lr (float, optional): The learning rate for the Adam optimizer. Defaults to 0.005.
        patience (int, optional): Epochs to wait for validation improvement before early stopping. Defaults to 20.
    """
    print("Starting ML Model training...")
    dataset = GlobalInventoryDataset(seq_len=50)
    
    total_size = len(dataset)
    if total_size < 10:
        print("Not enough training data available.")
        return

    # Partition dataset: 70% Train, 15% Validation, 15% Test
    train_size = int(0.7 * total_size)
    val_size = int(0.15 * total_size)
    test_size = total_size - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = random_split(dataset, [train_size, val_size, test_size])

    # Initialize data loaders for batching
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    
    num_tags = dataset.get_num_tags()
    model = GlobalQuantityGRU(num_tags=num_tags)
    
    # Configure optimization objective
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    
    best_val_loss = float('inf')
    patience_counter = 0
    best_model_state = None

    print(f"Starting training for {epochs} epochs...")
    
    for epoch in range(epochs):
        # ── Training Phase ──────────────────────────────────────────────────
        model.train()
        total_train_loss = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            logits = model(batch["features"], batch["tags"], batch["target_tag"])
            loss = criterion(logits, batch["label"])
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item()
            
        avg_train_loss = total_train_loss / max(1, len(train_loader))
        
        # ── Validation Phase ────────────────────────────────────────────────
        model.eval()
        total_val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                logits = model(batch["features"], batch["tags"], batch["target_tag"])
                loss = criterion(logits, batch["label"])
                total_val_loss += loss.item()
                
        avg_val_loss = total_val_loss / max(1, len(val_loader))
        
        # ── Early Stopping Check ────────────────────────────────────────────
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            # Clone state dict to CPU to prevent memory leaks during training
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1
            
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"Epoch {epoch+1}/{epochs} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}")
            
        if patience_counter >= patience:
            print(f"Early stopping triggered at epoch {epoch+1}")
            break

    # Restore the best validation weights
    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    # ── Final Testing Phase ─────────────────────────────────────────────
    model.eval()
    correct = 0
    total = 0
    test_loss = 0.0
    with torch.no_grad():
        for batch in test_loader:
            logits = model(batch["features"], batch["tags"], batch["target_tag"])
            loss = criterion(logits, batch["label"])
            test_loss += loss.item()
            
            preds = torch.argmax(logits, dim=-1)
            correct += (preds == batch["label"]).sum().item()
            total += batch["label"].size(0)

    avg_test_loss = test_loss / max(1, len(test_loader))
    test_accuracy = correct / max(1, total)
    
    print("-" * 40)
    print("FINAL EVALUATION ON TEST SET:")
    print(f"Test Loss: {avg_test_loss:.4f}")
    print(f"Test Accuracy: {test_accuracy*100:.2f}% ({correct}/{total})")
    print("-" * 40)

    # Persist the finalized model state and metadata dictionary
    torch.save({
        'model_state_dict': model.state_dict(),
        'tag_to_id': dataset.tag_to_id,
        'num_tags': num_tags
    }, MODEL_PATH)
    
    # Invalidate the global cache so the new model is loaded on the next inference query
    global _cached_model
    _cached_model = None
    
    print(f"Model saved to {MODEL_PATH}")

def load_model() -> tuple[GlobalQuantityGRU | None, dict | None]:
    """
    Load the pre-trained GRU model from disk, utilizing an in-memory cache if available.

    Returns:
        tuple: A tuple containing the initialized model and the tag-to-index mapping dictionary.
               Returns (None, None) if the model file does not exist.
    """
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
    Execute a forward pass through the trained GRU model to estimate the 
    remaining quantity level of a specified substance.

    Args:
        rfid_tag_id (str): The identifier of the substance to predict.

    Returns:
        str: The predicted categorical quantity ("A LOT", "MEDIUM", "LITTLE"). 
             Returns "UNKNOWN" if no model is found.
    """
    model, tag_to_id = load_model()
    if model is None:
        print("No trained model found. Defaulting to UNKNOWN.")
        return "UNKNOWN"
        
    # Extract the most recent global sessions for contextual input
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
    
    # Sort chronologically to match training format
    recent_sessions.reverse()
    
    # Initialize padded feature lists
    seq_features = []
    seq_tags = []
    seq_len = 50
    
    pad_len = seq_len - len(recent_sessions)
    for _ in range(pad_len):
        seq_features.append([0.0, 0.0, 0.0])
        seq_tags.append(0)
        
    # Process empirical session data into structural tensors
    for s in recent_sessions:
        dt = datetime.fromisoformat(s["taken_at"])
        tag = s["rfid_tag_id"]
        
        # Apply the pre-computed dictionary mapping or fallback to 0
        tag_idx = tag_to_id.get(tag, 0)
        dur = min(s["session_duration_s"] / 3600.0, 5.0)
        hour = dt.hour + dt.minute / 60.0
        
        seq_features.append([dur, math.sin(2 * math.pi * hour / 24.0), math.cos(2 * math.pi * hour / 24.0)])
        seq_tags.append(tag_idx)
        
    target_tag_idx = tag_to_id.get(rfid_tag_id, 0)
    
    # Cast sequential elements into PyTorch tensors with explicit batch dimensions
    features_t = torch.tensor([seq_features], dtype=torch.float32)
    tags_t = torch.tensor([seq_tags], dtype=torch.long)
    target_t = torch.tensor([target_tag_idx], dtype=torch.long)
    
    # Perform inference
    with torch.no_grad():
        logits = model(features_t, tags_t, target_t)
        pred_idx = torch.argmax(logits, dim=-1).item()
        
    return _label_map_inv[pred_idx]

if __name__ == "__main__":
    train_model()
