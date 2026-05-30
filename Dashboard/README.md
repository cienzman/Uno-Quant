# Smart Lab Inventory Dashboard

Streamlit dashboard to simulate an RFID-based smart lab inventory system. It also includes a mocked product depletion forecast chart.

## How to run

1. Open the folder in VS Code.
2. Create a Python virtual environment (optional but recommended).
```bash
python3 -m venv .venv
source .venv/bin/activate
```
3. Install the dependencies:

```bash
pip install -r requirements.txt
```

4. Launch the dashboard:

```bash
streamlit run dashboard.py
```

5. A page will open in your browser, usually at:

```text
http://localhost:8501
```

## Main Files

- `dashboard.py`: Streamlit interface.
- `inventory_logic.py`: Check-in/check-out logic and event management.
- `mock_data.py`: Initial simulated database.
- `simulated_rfid.py`: RFID event simulator.
- `forecast_mock.py`: Historical data and mocked forecast generator.
- `events_log.csv`: Event log, automatically created if it does not exist.

## Come usarla per la demo

- Use the buttons in the "RFID scan simulator" section to simulate scanning a bottle.

- If an item is `Present`, a scan changes its status to `Checked out`.

- If an item is `Checked out`, a new scan changes its status to `Present`.

- The dashboard updates the inventory, metrics, and event log.

## How to connect it to Arduino UNO R4 in the future

Replace the get_simulated_scan() function or the simulation buttons with a function that reads the real RFID tag from serial, a socket, a file, MQTT, Arduino App Lab Bridge, or another source.


## Mock forecast

The `Consumption forecast` tab shows dummy historical data, a linear projection, and an estimated depletion date. When the real model is ready, replace `build_mock_forecast(...)`in  `forecast_mock.py`.
