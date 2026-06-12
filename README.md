# 🧪 Uno Quant: Smart Laboratory Inventory

> **A cutting-edge, edge-computing research project carried out at [Necst Lab](https://necst.it/) in collaboration with the Arduino Team of Qualcomm.**
> 
> *The outcomes of this innovative project were proudly presented to Arduino CEO [Fabio Violante](https://www.linkedin.com/in/fabioviolante/).*

[![Arduino UNO Q](https://img.shields.io/badge/Hardware-Arduino_UNO_Q-00979D?style=for-the-badge&logo=arduino&logoColor=white)](https://arduino.cc)
[![Python](https://img.shields.io/badge/Backend-Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)

## 🌟 Overview

Welcome to **Uno Quant: Ambient Intelligence for Smart Laboratory Inventory**! This system revolutionizes how chemistry laboratories, research centers, and pharmacies track residual quantities of chemical substances. 

Born out of interviews with the Pharmaceutical Lab at Università di Pavia, this project solves a critical problem: manual inventory tracking (paper/Excel) leads to outdated information, missing data, and dangerous stockouts. Our solution keeps the user out of the loop as much as possible, using an **RFID-driven workflow**, **Edge AI**, and an intuitive dashboard—all running seamlessly on the new **Arduino UNO Q**.

### 🚀 Why This Matters
* **End-to-End Edge Architecture:** The entire stack (Data Layer, AI Layer, Backend, and Frontend) runs locally on the **Arduino UNO Q**—leveraging its Qualcomm® Dragonwing™ QRB2210 processor and STM32U585 microcontroller.
* **Non-Invasive AI:** No cameras. No load cells. The system uses advanced modeling on usage patterns (duration, cross-substance usage) to predict residual quantities without altering the chemist's workflow.
* **Innovative Data Collection:** Uses voice micro-feedback ("A LOT", "MEDIUM", "LITTLE") not as a permanent crutch, but as a clever UX trick to dynamically collect labeled data for continuous AI fine-tuning.
* **Hardware-Software Bridge:** Seamlessly integrates real-time hardware interrupts (C++) with a high-level Python application stack via the Arduino App Lab bridge.
* **Rich Data Integration:** Integrates dynamically with global scientific databases like PubChem and Sigma-Aldrich to enrich internal inventory metadata seamlessly.

---

## 🏗️ System Architecture

### 1. The Hardware: Arduino UNO Q
* **Dual Power:** Runs Debian OS on the Qualcomm QRB2210 and real-time C++ control on the STM32H5.
* **RFID Technology:** Uses MFRC522 sensors (similar to Decathlon's self-checkout) to detect when an item is taken from or returned to the pantry. 

### 2. The Code Pipeline
* **Hardware Layer (`sketch.ino`):** Reads RFID tags and sends data to the Linux subsystem using `Bridge.call("rfid_scan", tag)`.
* **Backend Layer (`main.py` & `db_utils.py`):** Captures the bridge event (`on_rfid_scan`), updates the SQLite database, and computes session duration.
* **Frontend Layer (`dashboard.py`):** A Streamlit dashboard that auto-refreshes to show real-time state, handles micro-feedback, and integrates voice assistant queries.
* **Intelligence Layer:** Predicts residual quantities when users skip manual feedback by analyzing usage durations and lab session patterns.

---

## 🛠️ How to Run the Project (Arduino App Lab)

This project is built using **Arduino App Lab**, a powerful visual and programmatic environment for managing the UNO Q board.

### Prerequisites
- An **Arduino UNO Q** board.
- Access to the **Arduino App Lab** environment.

### Step-by-Step Deployment
1. **Open the Project in App Lab:**
   Launch Arduino App Lab and import the `ambient-intelligence-internship` project folder.

2. **Deploy the Real-Time Sketch (C++):**
   - Navigate to the `sketch` directory.
   - Compile and flash `sketch.ino` to the STM32 microcontroller. This enables the RFID sensor bridge.

3. **Initialize the Environment (Python):**
   - Open the Linux terminal within App Lab (Debian OS).
   - Navigate to the `python` directory:
     ```bash
     cd python
     ```
   - Install dependencies:
     ```bash
     pip install -r requirements.txt
     ```
   - Initialize the SQLite database:
     ```bash
     python setup_db.py
     ```

4. **Launch the Core Services:**
   - Start the main Python process, which listens to the hardware bridge and serves the Streamlit dashboard:
     ```bash
     python main.py
     ```
   - The system is now active! The Streamlit dashboard is exposed on the board's local network IP at port `8501`.

---

## 🤝 Contributing

We welcome contributions from hardware enthusiasts, ML engineers, and full-stack developers! 

### Future Roadmap
- **Scale Hardware:** Implement stronger RFID antennas for passive, large-scale scanning without explicit "tap" actions. Enable distributed pantry tracking.
- **Scale AI:** Transition from synthetic data to large-scale real-world data, enhancing feature engineering to capture cross-substance dependencies.
- **Scale Customer Base:** Adapt the pipeline for integration into broader industrial pharmacy management systems.

To contribute:
1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---
*Built with at Necst Lab in collaboration with Arduino.*
