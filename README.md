# 🧪 Intelligent Environment: Smart Laboratory Inventory

Welcome to the **Smart Laboratory Inventory** project! This system is designed for chemistry laboratories, research centers, and pharmacies to autonomously track the residual quantity of chemical substances, preventing unseen stockouts and manual tracking errors.

This project uses an **RFID-driven workflow** backed by a **self-learning probabilistic machine learning model** and an interactive, highly visual Streamlit dashboard.

---

## 🏗️ Architecture & Pipeline

The system is designed to keep the user out of the loop as much as possible while maintaining highly accurate substance quantity estimates.

### 1. Hardware & Event Triggering
- **Current Prototype:** Uses simulated RFID scans triggered by buttons on the dashboard.
- **Future Integration:** An **Arduino UNO Q** paired with an RFID sensor. When a user takes a substance from the shelf, they scan the RFID tag, which sends an "IN_USE" event to the backend. Upon returning the item, they scan it again, triggering an "ON_SHELF" event and closing the session.

### 2. The Predictive Model (4 Phases)
Instead of relying on clunky scales or manual data entry, the system learns consumption patterns over time using a sophisticated Bayesian model:

* **Phase 0 (Duration Scaling):** When a session closes, the system calculates how long the substance was checked out. It scales the baseline consumption rate by comparing this session's duration to the historical average duration for that specific substance.
* **Phase 1 (Bayesian Updates):** The consumption rate isn't fixed; it's treated as a Gaussian distribution. After every session, the model performs a Bayesian Update, refining its belief about the `rate_per_usage` (mean) and its uncertainty (`rate_variance`) based on the newly observed duration.
* **Phase 2 (Micro-feedback Calibration):** To keep the model grounded without forcing users to weigh bottles, a quick, dismissible UI prompt appears when an item is returned: *"Is this substance enough for at least one more experiment?"*. Clicking YES or NO applies a directional correction factor, pulling the estimate up or pushing it down.
* **Phase 3 (Probabilistic Forecasting):** Using the learned variance and the average daily sessions, the dashboard generates three distinct depletion curves: **Optimistic (slow depletion)**, **Expected**, and **Pessimistic (fast depletion)**, plotting exactly when the lab might run out.

### 3. The Dashboard
The interactive Streamlit dashboard acts as the central hub:
- **Real-time Metrics:** View total items, present items, and checked-out items (with custom flashing visual alerts).
- **Sigma-Aldrich Integration:** Selecting an item dynamically loads its exact product page from Sigma-Aldrich directly inside the dashboard.
- **Alerts & Events:** Track expiration dates, low-stock warnings, and view a complete history of every check-out/check-in event.

---

## 🚀 How to Run the Project (For Colleagues)

Follow these steps to get the system running locally on your machine.

### Prerequisites
Make sure you have Python 3.10+ installed.

### Step 1: Clone and Setup Environment
Open your terminal and clone the repository (if you haven't already):
```bash
# Navigate to the project directory
cd SMART_LAB_INVENTORY

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Linux/Mac:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install the required packages
pip install -r requirements.txt
```

### Step 2: Initialize the Database
The project uses SQLite. Before running the dashboard, you must initialize the database and seed it with demo substances:
```bash
python setup_db.py
```
*(Note: If you are upgrading from an older version of the database, you can run `python upgrade_db_v2.py` instead to preserve existing data).*

### Step 3: Launch the Dashboard
Run the Streamlit application:
```bash
cd Dashboard
streamlit run dashboard.py
```
A browser window should automatically open at `http://localhost:8501`.

to reset the db: 
```bash
cd ArduinoApps/smart-lab-inventory/python
python3 setup_db.py
```


### Step 4: Try the Demo Workflow
1. In the dashboard sidebar, under **Demo controls**, click the button for **"Sodium Chloride"**.
2. Notice the "Checked out" metric flashes and the event is logged. 
3. Wait a few seconds, then click the **"Sodium Chloride"** button again to return it.
4. The system will calculate the consumption based on how long you waited. A **Micro-feedback question** will pop up at the top asking if there is enough for another experiment. Answer it to calibrate the model!
5. Navigate to the **Consumption forecast** tab to see the updated probabilistic depletion curves.

---

## 📂 Project Structure

```text
INTELLIGENT_ENVIRONMENT/
├── .gitignore
├── README.md
├── db_utils.py               # Core database interaction logic
├── setup_db.py               # Script to create schemas and seed data
├── upgrade_db.py             # Script for Phase 1 & 2 schema updates
├── upgrade_db_v2.py          # Script for Phase 3 schema updates (Sigma-Aldrich)
├── db/                       # Folder containing the SQLite database
│   └── inventory.db
└── Dashboard/
    ├── dashboard.py          # Main Streamlit application
    ├── predictive_model.py   # Machine Learning logic (Bayesian updates, scaling)
    ├── forecast_mock.py      # Generates the probabilistic forecast curves
    ├── inventory_logic.py    # Search and alert filtering utilities
    ├── simulated_rfid.py     # Mock RFID scanner inputs
    └── requirements.txt      # Python dependencies
```
