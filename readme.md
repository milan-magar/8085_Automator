# Automation Suite (Workflow & 8085 Simulator)

A modern, multi-threaded Python desktop application designed to automate repetitive screen interactions and streamline 8085 microprocessor simulator tasks. 

It features a drag-and-drop workflow builder, auto-stitching of screenshots, real-time visual feedback, advanced simulator calibration, and an automation pipeline to chain tasks together.

---

## 🚀 Features

* **Screenshot Workflow:** Build a sequence of actions (`Click`, `Screenshot`, `Wait`, `Keypress`). Drag and drop to reorder. Automatically merges all captured screenshots into one single, vertically stitched image.
* **8085 Simulator Automation:**
  * **Auto-Calibration:** Visually draw a box over your simulator's keypad and function buttons to automatically map coordinates.
  * **Address Parsing:** Paste code like `9001H: 21 00 80` and the app automatically extracts the starting address and types only the opcodes.
  * **Live Highlighting:** Watch the app highlight the exact byte it is typing in real-time.
  * **Command Stage:** Automatically detects the `76` (`HLT`) opcode, executes the program, and checks the output address.
  * **File Import:** Read `Input:`, `Command:`, and `Output:` blocks directly from a `.txt` file.
* **Automation Pipeline:** Use the floating green **Run Pipeline** button to automatically execute the Input Stage, Command Stage, and Screenshot Workflow back-to-back.
* **Multi-Theme Support:** Choose between **Light**, **Dark**, and **Hacker** themes. Your theme choice is saved and persists across sessions.
* **Emergency Stop:** Hit `Ctrl+Shift+Q` at any time to instantly abort all running automations and bring the window back to the front.

---

## 📦 Prerequisites

You need **Python 3.8+** installed on your system.

Install the required libraries via terminal or command prompt:

```bash
pip install mss pillow pyautogui keyboard
```

> **Note:** The `keyboard` library may require administrative privileges on some operating systems (especially macOS and Linux) to register global hotkeys.

---

## 🛠️ How to Run

Navigate to the project directory and run:

```bash
python main.py
```

---

## 📖 How to Use

### 1. The Global Settings (Top Bar)
* **Output Folder:** Set the directory where your screenshots, merged images, and text files will be saved. Both tabs share this folder.
* **Theme:** Switch between **Light**, **Dark**, and **Hacker** modes.

### 2. Screenshot Workflow Tab
1. Set how many **Iterations** you want the workflow to run.
2. Click `+ Click`, `+ Snap` (Screenshot), `+ Wait`, or `+ Key` to add steps.
3. Double-click any step in the list to edit its exact coordinates, delay, or keys.
4. Drag and drop steps up or down to reorder them.
5. Click **▶ Run** to execute. If **Auto-merge** is checked, it will create `merged_screenshots.png` in the output folder.

### 3. 8085 Simulator Tab

#### Step A: Calibration *(Do this first)*
1. Click **Auto-Cal 0-F**. The screen will dim. Click and drag a box perfectly around your **16 Hex keys** on the simulator.
2. Click **Auto-Cal Funcs**. Drag a box around your **8 Function keys** (`Reset`, `Next`, `Go`, etc.).
3. You can verify your coordinates by clicking **Check Cal**.

#### Step B: Input Stage
1. Paste your code (e.g., `8000H: 05 11 22`) into the box. The address `8000` will auto-fill.
2. Adjust the **Delay** slider if your simulator is slow.
3. Click **▶ Run Input Stage**.

#### Step C: Command Stage
1. Paste your command code (ensure it contains `76` if you want it to execute).
2. Include an **Output Addr** (e.g., `8050`) if you want the app to jump to that memory address after execution.
3. Click **▶ Run Command Stage**.

### 4. The Pipeline (Green FAB)
Located at the bottom right of the screen:
* **Left-Click:** Runs the automation chain based on your current settings.
* **Right-Click:** Opens a small menu to check/uncheck which stages you want to include in the pipeline.

---

## 📁 Generated Files

The app automatically creates and updates these files in the same directory as `main.py`:

* `workflow.json` – Stores your saved Screenshot Workflow steps.
* `8085_calibration.json` – Stores your calibrated X/Y coordinates for the simulator.
* `settings.json` – Remembers your last used UI theme.
* `outputs/` – The default folder where screenshots and merged images are saved.

---

## ⚠️ Troubleshooting

* **Nothing is clicking in the simulator?**  
  Re-run the calibration process. Windows display scaling (DPI) can sometimes shift coordinates if not calibrated directly on the screen.
* **The Emergency Stop (`Ctrl+Shift+Q`) isn't working?**  
  Try running your terminal or IDE as an **Administrator**. The `keyboard` library needs system-level access to listen for global hotkeys.