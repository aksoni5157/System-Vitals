# ⚙ System Vitals AI — Desktop Edition

> **"One AI. Two Lives. Your Device & Your Digital Wellbeing."**

A real-time desktop dashboard that monitors **hardware health** (CPU, RAM, Storage, Battery) and **digital wellbeing** (session time, break reminders) through an explainable AI scoring system.

## Offline Vita AI chat setup (Windows)

Vita AI chat uses the local **Qwen3 0.6B** model through Ollama. The model is generative and runs on this computer; the existing system score/diagnosis engine remains the separate explainable rules based component. No Python inference package or cloud API is required.

Install Ollama and download the model once while online (the model download is about 523 MB):

```powershell
winget install --id Ollama.Ollama -e
# Open a new PowerShell window after installation
ollama pull qwen3:0.6b
```

After the download completes, Vita AI uses Ollama at `localhost:11434` and can generate responses without internet access. Ollama keeps the model loaded between messages, and the chat streams response chunks while retaining recent conversation context. If Ollama or the model is unavailable, Vita AI shows a clear service or model error instead of presenting a scripted response as generated text.

Run the app from the project folder:

```powershell
.\.venv\Scripts\python.exe app.py
```

## 👥 Team Vitals

| Role | Name |
|------|------|
| **Team Leader** | Akash Soni |
| **Members** | Ansh Jangid, Abhinav Pratap Singh, Ansh Porwal, Anmol Tanwar |
| **Supervisor** | Dr. Vishal Srivastava |

## 🏗 Architecture

```
app.py                  — Main GUI dashboard (CustomTkinter)
├── ai_brain.py         — AI reasoning engine (Device Doctor + Wellness Coach)
├── database_manager.py — Thread-safe SQLite data layer
├── telemetry_engine.py — Background hardware telemetry sampler (psutil)
└── requirements.txt    — Python dependencies
```

**Data flow:** `psutil` → `TelemetryEngine` (background thread) → `AIBrain` (scoring) → `Dashboard` (3-column GUI) → `DatabaseManager` (SQLite persistence)

## 📋 Requirements

- **Python 3.7+**
- `customtkinter >= 5.2.0`
- `psutil >= 5.9.0`

## 🚀 Installation & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the dashboard
python app.py
```

## ✨ Features

### 🖥 Live Device Health (Left Panel)
- Real-time CPU load, RAM usage, storage health, and battery SoH
- Color-coded progress bars (green → yellow → red)
- Platform-aware (handles desktops without batteries gracefully)

### 🧠 Digital Wellbeing (Center Panel)
- Active session timer with break countdown
- Focus status badge (Focused → Stretch Recommended → Overdue)
- "I Took a Break" button to reset session tracking
- Break reminder popups every 45 minutes

### 🩺 AI Brain Diagnosis (Right Panel)
- **Life Balance Score** (0–100) — fully explainable, every point deducted has a named reason
- **Device Doctor** persona: diagnoses CPU throttling risk, RAM pressure, storage/battery concerns
- **Wellness Coach** persona: evaluates unbroken session time against health guidelines
- **Cross-domain correlation**: detects compounding risk (high CPU + long session + dismissed reminders)
- Plain-language explanation feed

### ⚡ Action Bar
- **Cooling Mode**: Lowers app process priority to reduce thermal load
- **Battery Saver**: Reduces telemetry sampling and UI refresh frequency
- **Export Report**: Full ecosystem analytics exported as JSON

## 📊 Database Schema

**`telemetry_logs`** — Periodic hardware + score snapshots  
**`session_logs`** — Focus session start/end times with break tracking

## 📄 License

This project was developed as an academic project.
