"""
Workflow Automator + 8085 Simulator Automation.
Requires:
    pip install mss pillow pyautogui keyboard
"""

import ctypes
import io
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path

import mss
from PIL import Image

try:
    import keyboard
except ImportError:
    keyboard = None

if sys.platform == "win32":
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_FILE      = os.path.join(BASE_DIR, "workflow.json")
CALIBRATION_FILE   = os.path.join(BASE_DIR, "8085_calibration.json")
SETTINGS_FILE      = os.path.join(BASE_DIR, "settings.json")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")


# --------------------------------------------------------------------------- #
# THEME MANAGEMENT
# --------------------------------------------------------------------------- #

THEMES = {
    "light": {
        "bg": "#f0f0f0", "fg": "#000000", "field_bg": "#ffffff", "field_fg": "#000000",
        "btn_bg": "#e0e0e0", "btn_fg": "#000000", "select_bg": "#0078d7", "select_fg": "#ffffff",
        "text_bg": "#ffffff", "text_fg": "#000000", "log_bg": "#f5f5f5", "log_fg": "#333333",
        "highlight": "#ffeb3b", "highlight_fg": "#000000", "fab_bg": "#28a745", "fab_fg": "#ffffff"
    },
    "dark": {
        "bg": "#2b2b2b", "fg": "#ffffff", "field_bg": "#1e1e1e", "field_fg": "#ffffff",
        "btn_bg": "#3c3f41", "btn_fg": "#ffffff", "select_bg": "#4a90e2", "select_fg": "#ffffff",
        "text_bg": "#1e1e1e", "text_fg": "#a9b7c6", "log_bg": "#1e1e1e", "log_fg": "#a9b7c6",
        "highlight": "#4a90e2", "highlight_fg": "#ffffff", "fab_bg": "#28a745", "fab_fg": "#ffffff"
    },
    "hacker": {
        "bg": "#000000", "fg": "#00ff00", "field_bg": "#0a0a0a", "field_fg": "#00ff00",
        "btn_bg": "#111111", "btn_fg": "#00ff00", "select_bg": "#005500", "select_fg": "#00ff00",
        "text_bg": "#000000", "text_fg": "#00ff00", "log_bg": "#000000", "log_fg": "#00ff00",
        "highlight": "#005500", "highlight_fg": "#00ff00", "fab_bg": "#003300", "fab_fg": "#00ff00"
    }
}

def apply_theme(root, theme_name):
    c = THEMES[theme_name]
    style = ttk.Style(root)
    style.theme_use("clam")
    
    # Base
    style.configure(".", background=c["bg"], foreground=c["fg"], font=("Segoe UI", 9))
    style.configure("TFrame", background=c["bg"])
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    
    # Frames & Labels
    style.configure("TLabelframe", background=c["bg"], foreground=c["fg"], bordercolor=c["fg"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
    
    # Buttons
    style.configure("TButton", background=c["btn_bg"], foreground=c["btn_fg"], padding=2, bordercolor=c["fg"])
    style.map("TButton", background=[("active", c["select_bg"])])
    style.configure("Green.TButton", foreground="green", background=c["btn_bg"])
    style.configure("Red.TButton", foreground="red", background=c["btn_bg"])
    
    # Inputs
    style.configure("TEntry", fieldbackground=c["field_bg"], foreground=c["field_fg"], insertcolor=c["fg"])
    style.configure("TCombobox", fieldbackground=c["field_bg"], foreground=c["field_fg"], arrowcolor=c["fg"])
    style.configure("TSpinbox", fieldbackground=c["field_bg"], foreground=c["field_fg"], arrowcolor=c["fg"])
    
    # Combobox Listbox (Dropdown)
    root.option_add("*TCombobox*Listbox.background", c["field_bg"])
    root.option_add("*TCombobox*Listbox.foreground", c["field_fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])
    
    # Checkbuttons
    style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
    style.map("TCheckbutton", background=[("active", c["bg"])])
    
    # Notebook
    style.configure("TNotebook", background=c["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=c["btn_bg"], foreground=c["btn_fg"], padding=[6, 3])
    style.map("TNotebook.Tab", background=[("selected", c["select_bg"])], foreground=[("selected", c["select_fg"])])
    
    root.configure(bg=c["bg"])
    return c

# --------------------------------------------------------------------------- #
# IMAGE STITCHING UTILITY
# --------------------------------------------------------------------------- #

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}

def collect_images(folder: Path) -> list[Path]:
    if not folder.is_dir(): return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)

def stitch_images_to_single_png(folder: Path, *, log_callback=None) -> int:
    images = collect_images(folder)
    if not images: raise ValueError(f"No images found in {folder}")
    if log_callback: log_callback(f"  Stitching {len(images)} image(s)...")

    loaded_imgs = []
    for p in images:
        try: loaded_imgs.append(Image.open(p).convert("RGB"))
        except Exception as e:
            if log_callback: log_callback(f"  ! skipping {p.name}: {e}")

    if not loaded_imgs: raise ValueError("No valid images to stitch.")

    max_width = max(img.width for img in loaded_imgs)
    total_height = sum(img.height for img in loaded_imgs)

    combined = Image.new("RGB", (max_width, total_height), (255, 255, 255))
    y_offset = 0
    
    for img in loaded_imgs:
        combined.paste(img, ((max_width - img.width) // 2, y_offset))
        y_offset += img.height

    out_path = folder / "merged_screenshots.png"
    combined.save(str(out_path), format="PNG")
    if log_callback: log_callback(f"  Merged image saved → {out_path.name}")
    return len(loaded_imgs)

# --------------------------------------------------------------------------- #
# STEP HELPERS & PICKERS
# --------------------------------------------------------------------------- #

def default_step(kind: str) -> dict:
    if kind == "click": return {"type": "click", "x": 100, "y": 100, "button": "left", "clicks": 1}
    if kind == "screenshot": return {"type": "screenshot", "left": 0, "top": 0, "width": 800, "height": 600}
    if kind == "wait": return {"type": "wait", "seconds": 1.0}
    if kind == "key": return {"type": "key", "keys": "enter"}
    raise ValueError(kind)

def step_summary(step: dict) -> str:
    t = step.get("type")
    if t == "click": return f"Click ({step['x']},{step['y']}) {step.get('button','left')} x{step.get('clicks',1)}"
    if t == "screenshot": return f"Screenshot ({step['left']},{step['top']}) {step['width']}x{step['height']}"
    if t == "wait": return f"Wait {step['seconds']}s"
    if t == "key": return f"Key: {step['keys']}"
    return "?"

def _make_overlay() -> tk.Toplevel:
    top = tk.Toplevel()
    top.attributes("-fullscreen", True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.25)
    top.config(bg="black", cursor="crosshair")
    top.lift()
    return top

def overlay_pick_point():
    result = {"pos": None}
    top = _make_overlay()
    tk.Label(top, text="Click target location  (Esc to cancel)", bg="black", fg="white", font=("Segoe UI", 14, "bold")).pack(pady=40)
    def on_click(e):
        result["pos"] = (e.x_root, e.y_root)
        top.destroy()
    top.bind("<Button-1>", on_click)
    top.bind("<Escape>", lambda e: top.destroy())
    top.focus_force()
    top.wait_window()
    return result["pos"]

def overlay_pick_region():
    result = {"box": None}
    top = _make_overlay()
    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(top.winfo_screenwidth() // 2, 30, text="Drag to select region  (Esc to cancel)", fill="white", font=("Segoe UI", 14, "bold"))

    state = {"x0": 0, "y0": 0, "rect": None}
    def on_press(e):
        state["x0"], state["y0"] = e.x_root, e.y_root
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff5555", width=2)
    def on_drag(e):
        if not state["rect"]: return
        cx0 = state["x0"] - top.winfo_rootx()
        cy0 = state["y0"] - top.winfo_rooty()
        canvas.coords(state["rect"], cx0, cy0, e.x, e.y)
    def on_release(e):
        x1, y1 = min(state["x0"], e.x_root), min(state["y0"], e.y_root)
        x2, y2 = max(state["x0"], e.x_root), max(state["y0"], e.y_root)
        if x2 - x1 > 2 and y2 - y1 > 2:
            result["box"] = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
        top.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", lambda e: top.destroy())
    top.focus_force()
    top.wait_window()
    return result["box"]

class StepEditor(tk.Toplevel):
    def __init__(self, master, step: dict):
        super().__init__(master)
        self.work = dict(step)
        self.result = None
        self.title(f"Edit {self.work['type'].title()} Step")
        self.attributes("-topmost", True)
        self.transient(master)
        self.resizable(False, False)

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        kind = self.work["type"]
        if kind == "click": self._build_click(body)
        elif kind == "screenshot": self._build_screenshot(body)
        elif kind == "wait": self._build_wait(body)
        elif kind == "key": self._build_key(body)

        btns = ttk.Frame(self, padding=(8, 0, 8, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right", padx=(4, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        self.update_idletasks()
        try:
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            w, h   = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{mx + (mw - w)//2}+{my + (mh - h)//2}")
        except Exception: pass

    def _build_click(self, body):
        self.x_var = tk.StringVar(value=str(self.work.get("x", 0)))
        self.y_var = tk.StringVar(value=str(self.work.get("y", 0)))
        self.button_var = tk.StringVar(value=self.work.get("button", "left"))
        self.clicks_var = tk.StringVar(value=str(self.work.get("clicks", 1)))

        ttk.Label(body, text="X:").grid(row=0, column=0, sticky="e", pady=2)
        ttk.Entry(body, textvariable=self.x_var, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(body, text="Y:").grid(row=0, column=2, sticky="e", padx=(8, 0), pady=2)
        ttk.Entry(body, textvariable=self.y_var, width=8).grid(row=0, column=3, sticky="w", padx=4, pady=2)

        ttk.Label(body, text="Button:").grid(row=1, column=0, sticky="e", pady=2)
        ttk.Combobox(body, textvariable=self.button_var, values=["left", "right", "middle"], state="readonly", width=6).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(body, text="Clicks:").grid(row=1, column=2, sticky="e", padx=(8, 0), pady=2)
        ttk.Spinbox(body, from_=1, to=10, textvariable=self.clicks_var, width=6).grid(row=1, column=3, sticky="w", padx=4, pady=2)

        ttk.Button(body, text="Pick Position on Screen", command=self._pick_point).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

    def _build_screenshot(self, body):
        self.left_var = tk.StringVar(value=str(self.work.get("left", 0)))
        self.top_var = tk.StringVar(value=str(self.work.get("top", 0)))
        self.width_var = tk.StringVar(value=str(self.work.get("width", 800)))
        self.height_var = tk.StringVar(value=str(self.work.get("height", 600)))

        ttk.Label(body, text="Left:").grid(row=0, column=0, sticky="e", pady=2)
        ttk.Entry(body, textvariable=self.left_var, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(body, text="Top:").grid(row=0, column=2, sticky="e", padx=(8, 0), pady=2)
        ttk.Entry(body, textvariable=self.top_var, width=8).grid(row=0, column=3, sticky="w", padx=4, pady=2)

        ttk.Label(body, text="Width:").grid(row=1, column=0, sticky="e", pady=2)
        ttk.Entry(body, textvariable=self.width_var, width=8).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(body, text="Height:").grid(row=1, column=2, sticky="e", padx=(8, 0), pady=2)
        ttk.Entry(body, textvariable=self.height_var, width=8).grid(row=1, column=3, sticky="w", padx=4, pady=2)

        ttk.Button(body, text="Pick Region on Screen", command=self._pick_region).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

    def _build_wait(self, body):
        self.sec_var = tk.StringVar(value=str(self.work.get("seconds", 1.0)))
        ttk.Label(body, text="Seconds:").grid(row=0, column=0, sticky="e", pady=2)
        ttk.Entry(body, textvariable=self.sec_var, width=10).grid(row=0, column=1, sticky="w", padx=4, pady=2)

    def _build_key(self, body):
        self.key_var = tk.StringVar(value=self.work.get("keys", "enter"))
        ttk.Label(body, text="Keys:").grid(row=0, column=0, sticky="e", pady=2)
        ttk.Entry(body, textvariable=self.key_var, width=20).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(body, text="Examples: enter, tab, esc, ctrl+s").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _pick_point(self):
        self.withdraw()
        try: pos = overlay_pick_point()
        finally: self.deiconify()
        if pos:
            self.x_var.set(str(pos[0]))
            self.y_var.set(str(pos[1]))

    def _pick_region(self):
        self.withdraw()
        try: box = overlay_pick_region()
        finally: self.deiconify()
        if box:
            self.left_var.set(str(box["left"]))
            self.top_var.set(str(box["top"]))
            self.width_var.set(str(box["width"]))
            self.height_var.set(str(box["height"]))

    def _on_ok(self):
        try:
            t = self.work["type"]
            if t == "click":
                self.work["x"] = int(self.x_var.get())
                self.work["y"] = int(self.y_var.get())
                self.work["button"] = self.button_var.get()
                self.work["clicks"] = int(self.clicks_var.get())
            elif t == "screenshot":
                self.work["left"] = int(self.left_var.get())
                self.work["top"] = int(self.top_var.get())
                self.work["width"] = int(self.width_var.get())
                self.work["height"] = int(self.height_var.get())
            elif t == "wait":
                self.work["seconds"] = float(self.sec_var.get())
            elif t == "key":
                self.work["keys"] = self.key_var.get().strip()
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e), parent=self)
            return
        self.result = self.work
        self.destroy()

# --------------------------------------------------------------------------- #
# FIRST TAB: Screenshot Workflow
# --------------------------------------------------------------------------- #

class ScreenWorkflowTab(ttk.Frame):
    def __init__(self, parent, root_app):
        super().__init__(parent)
        self.root_app = root_app
        self.steps = []
        self.drag_from = None
        self.log_q = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = None

        self._build_ui()
        self._load_workflow()

        if not self.steps:
            self.steps = [{"type": "wait", "seconds": 0.5}, {"type": "screenshot", "left": 0, "top": 0, "width": 800, "height": 600}]
            self.refresh_listbox()

        self.root_app.root.after(100, self.poll_log)

    def _build_ui(self):
        # Top controls
        top = ttk.Frame(self, padding=5)
        top.pack(fill="x")
        ttk.Label(top, text="Iterations:").pack(side="left")
        self.iter_var = tk.StringVar(value="1")
        ttk.Spinbox(top, from_=1, to=9999, textvariable=self.iter_var, width=5).pack(side="left", padx=(2, 8))

        self.minimize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Minimize run", variable=self.minimize_var).pack(side="left", padx=(0, 8))

        self.auto_stitch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto-merge", variable=self.auto_stitch_var).pack(side="left", padx=(0, 8))

        self.run_btn = ttk.Button(top, text="▶ Run", command=lambda: self.run_workflow())
        self.run_btn.pack(side="left", padx=2)
        self.stop_btn = ttk.Button(top, text="■ Stop", command=self.stop_workflow, state="disabled")
        self.stop_btn.pack(side="left", padx=2)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self.status_var, foreground="#2a8").pack(side="right")

        # Middle Panes
        mid = ttk.PanedWindow(self, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # Left side: Steps
        left = ttk.Frame(mid)
        mid.add(left, weight=1)
        ttk.Label(left, text="Workflow Steps (drag to reorder)").pack(anchor="w")

        # Buttons Packed to BOTTOM first (Ensures they never crop out)
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", side="bottom", pady=(4, 0))
        
        # Use grid for buttons to guarantee they fit
        row1 = ttk.Frame(btn_frame)
        row1.pack(fill="x", pady=(0, 2))
        for i in range(4): row1.columnconfigure(i, weight=1)
        
        ttk.Button(row1, text="+ Click", command=lambda: self.add_step("click")).grid(row=0, column=0, sticky="ew", padx=1)
        ttk.Button(row1, text="+ Snap", command=lambda: self.add_step("screenshot")).grid(row=0, column=1, sticky="ew", padx=1)
        ttk.Button(row1, text="+ Wait", command=lambda: self.add_step("wait")).grid(row=0, column=2, sticky="ew", padx=1)
        ttk.Button(row1, text="+ Key", command=lambda: self.add_step("key")).grid(row=0, column=3, sticky="ew", padx=1)
        
        row2 = ttk.Frame(btn_frame)
        row2.pack(fill="x")
        for i in range(3): row2.columnconfigure(i, weight=1)
        
        ttk.Button(row2, text="Edit", command=self.edit_selected).grid(row=0, column=0, sticky="ew", padx=1)
        ttk.Button(row2, text="Delete", command=self.delete_selected).grid(row=0, column=1, sticky="ew", padx=1)
        ttk.Button(row2, text="Clear", command=self.clear_all).grid(row=0, column=2, sticky="ew", padx=1)

        # Listbox
        lb_frame = ttk.Frame(left)
        lb_frame.pack(fill="both", expand=True, pady=(2, 4))

        self.listbox = tk.Listbox(lb_frame, activestyle="none", selectmode="browse",
                                  font=("Consolas", 9), highlightthickness=1, bd=0, exportselection=False)
        lsb = ttk.Scrollbar(lb_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=lsb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

        self.listbox.bind("<Double-Button-1>", lambda e: self.edit_selected())
        
        # Drag & Drop bindings
        self.listbox.bind("<ButtonPress-1>", self._on_lb_press)
        self.listbox.bind("<B1-Motion>", self._on_lb_motion)
        self.listbox.bind("<ButtonRelease-1>", self._on_lb_release)
        self.root_app.root.bind("<ButtonRelease-1>", self._on_global_release, add="+")

        # Right side: Log
        right = ttk.Frame(mid)
        mid.add(right, weight=1)
        
        log_header = ttk.Frame(right)
        log_header.pack(fill="x")
        ttk.Label(log_header, text="Log").pack(side="left")
        ttk.Button(log_header, text="Clear", command=self._clear_log).pack(side="right")

        self.log_text = tk.Text(right, wrap="word", state="disabled", font=("Consolas", 8), bd=1, relief="solid")
        self.log_text.pack(fill="both", expand=True, pady=(2, 0))

    def update_theme(self, c):
        self.listbox.config(bg=c["field_bg"], fg=c["field_fg"], selectbackground=c["select_bg"], selectforeground=c["select_fg"])
        self.log_text.config(bg=c["log_bg"], fg=c["log_fg"], insertbackground=c["fg"])

    def _selected_index(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def refresh_listbox(self, select=None):
        if select is None:
            sel = self.listbox.curselection()
            select = sel[0] if sel else None
        self.listbox.delete(0, "end")
        for i, s in enumerate(self.steps):
            self.listbox.insert("end", f"{i + 1:>2}.  {step_summary(s)}")
        if select is not None and 0 <= select < len(self.steps):
            self.listbox.selection_set(select)
            self.listbox.activate(select)
            self.listbox.see(select)

    def add_step(self, kind):
        dlg = StepEditor(self.root_app.root, default_step(kind))
        self.root_app.root.wait_window(dlg)
        if dlg.result is not None:
            self.steps.append(dlg.result)
            self.refresh_listbox(select=len(self.steps) - 1)
            self.save_workflow()

    def edit_selected(self):
        idx = self._selected_index()
        if idx is None: return
        dlg = StepEditor(self.root_app.root, self.steps[idx])
        self.root_app.root.wait_window(dlg)
        if dlg.result is not None:
            self.steps[idx] = dlg.result
            self.refresh_listbox(select=idx)
            self.save_workflow()

    def delete_selected(self):
        idx = self._selected_index()
        if idx is None: return
        del self.steps[idx]
        new_sel = min(idx, len(self.steps) - 1) if self.steps else None
        self.refresh_listbox(select=new_sel)
        self.save_workflow()

    def clear_all(self):
        if self.steps and messagebox.askyesno("Clear All", "Delete all steps?", parent=self.root_app.root):
            self.steps.clear()
            self.refresh_listbox()
            self.save_workflow()

    # --- Drag and Drop Logic ---
    def _on_lb_press(self, event): 
        self.drag_from = self.listbox.nearest(event.y)
        self.listbox.config(cursor="fleur")
        
    def _on_lb_motion(self, event):
        if self.drag_from is None: return
        i = self.listbox.nearest(event.y)
        if i != self.drag_from and 0 <= i < len(self.steps):
            self.steps.insert(i, self.steps.pop(self.drag_from))
            self.drag_from = i
            self.refresh_listbox(select=i)
            
    def _on_lb_release(self, event):
        if self.drag_from is not None:
            self.drag_from = None
            self.listbox.config(cursor="")
            self.save_workflow()
            
    def _on_global_release(self, event):
        if getattr(self, "drag_from", None) is not None:
            self.drag_from = None
            self.listbox.config(cursor="")
            self.save_workflow()

    def _highlight_step(self, idx):
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self.listbox.see(idx)

    def run_workflow(self, is_pipeline=False, callback=None):
        if self.worker and self.worker.is_alive(): return
        if not self.steps:
            messagebox.showinfo("Nothing to run", "Add at least one step first.", parent=self.root_app.root)
            if callback: callback(False)
            return
        try:
            iterations = int(self.iter_var.get())
            if iterations < 1: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid iterations", "Enter a whole number >= 1.", parent=self.root_app.root)
            if callback: callback(False)
            return

        target_folder = self.root_app.shared_folder_var.get().strip()
        if not target_folder:
            messagebox.showerror("Invalid Folder", "Please provide a valid output folder path.", parent=self.root_app.root)
            if callback: callback(False)
            return

        try: os.makedirs(target_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Folder Error", f"Could not create folder:\n{e}", parent=self.root_app.root)
            if callback: callback(False)
            return

        self.stop_flag.clear()
        steps_snapshot = [dict(s) for s in self.steps]

        self.status_var.set(f"Running {iterations} iteration(s)…")
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        if self.minimize_var.get() and not is_pipeline: self.root_app.root.iconify()

        self.worker = threading.Thread(
            target=self._worker_main,
            args=(steps_snapshot, iterations, self.auto_stitch_var.get(), target_folder, callback),
            daemon=True,
        )
        self.worker.start()

    def _worker_main(self, steps, iterations, auto_stitch, target_folder, callback=None):
        success = False
        try:
            with mss.MSS() as sct: # FIXED: mss.mss() deprecation warning
                for it in range(1, iterations + 1):
                    if self.stop_flag.is_set(): break
                    self.log_q.put(f"=== Iteration {it}/{iterations} ===")
                    for idx, step in enumerate(steps, 1):
                        if self.stop_flag.is_set(): break
                        
                        self.root_app.root.after(0, lambda i=idx-1: self._highlight_step(i))
                        
                        try:
                            t = step["type"]
                            if t == "click":
                                clicks = int(step.get("clicks", 1))
                                pyautogui.click(x=int(step["x"]), y=int(step["y"]), clicks=clicks,
                                                button=step.get("button", "left"), interval=0.05 if clicks > 1 else 0.0)
                                self.log_q.put(f"  [{idx}] click ({step['x']},{step['y']}) {step.get('button','left')} x{clicks}")
                            elif t == "screenshot":
                                region = {"left": int(step["left"]), "top": int(step["top"]),
                                          "width": int(step["width"]), "height": int(step["height"])}
                                shot = sct.grab(region)
                                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                                fname = os.path.join(target_folder, f"iter{it:03d}_step{idx:02d}.png")
                                img.save(fname)
                                self.log_q.put(f"  [{idx}] screenshot → {os.path.basename(fname)}")
                            elif t == "wait":
                                sec = float(step["seconds"])
                                self.log_q.put(f"  [{idx}] wait {sec}s")
                                end = time.time() + sec
                                while time.time() < end:
                                    if self.stop_flag.is_set(): break
                                    time.sleep(0.05)
                            elif t == "key":
                                keys = step["keys"]
                                if "+" in keys: pyautogui.hotkey(*[k.strip() for k in keys.split("+")])
                                else: pyautogui.press(keys)
                                self.log_q.put(f"  [{idx}] key: {keys}")
                        except Exception as e:
                            self.log_q.put(f"  [{idx}] ERROR: {e}")
                            self.stop_flag.set()
                            break

            if auto_stitch and not self.stop_flag.is_set():
                self.log_q.put("Merging screenshots...")
                try:
                    def log_cb(msg): self.log_q.put(msg)
                    n = stitch_images_to_single_png(Path(target_folder), log_callback=log_cb)
                    self.log_q.put(f"  Successfully merged {n} images.")
                except Exception as e:
                    self.log_q.put(f"  Merge failed: {e}")
            
            success = not self.stop_flag.is_set()
        except Exception as e:
            self.log_q.put(f"FATAL: {e}")
            traceback.print_exc()
        finally:
            self.root_app.root.after(0, lambda: self.listbox.selection_clear(0, "end"))
            self.log_q.put("__DONE__")
            if callback:
                self.root_app.root.after(0, lambda: callback(success))

    def stop_workflow(self):
        self.stop_flag.set()
        self.status_var.set("Stopping…")

    def poll_log(self):
        done = False
        try:
            while True:
                msg = self.log_q.get_nowait()
                if msg == "__DONE__": done = True
                else: self._append_log(msg)
        except queue.Empty: pass

        if done or (self.worker and not self.worker.is_alive()):
            self._on_run_done()
        else:
            self.root_app.root.after(100, self.poll_log)

    def _force_ui_ready(self):
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Ready")

    def _append_log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _on_run_done(self):
        if self.minimize_var.get(): self.root_app.root.deiconify()
        self._force_ui_ready()
        self._append_log("=== Done ===")

    def save_workflow(self):
        try:
            data = {"iterations": int(self.iter_var.get() or 1), "steps": self.steps}
            with open(WORKFLOW_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[save_workflow] {e}")

    def _load_workflow(self):
        if not os.path.exists(WORKFLOW_FILE): return
        try:
            with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.steps = data.get("steps", [])
            self.iter_var.set(str(data.get("iterations", 1)))
            self.refresh_listbox()
        except Exception as e:
            print(f"[load_workflow] {e}")

# --------------------------------------------------------------------------- #
# SECOND TAB: 8085 Simulator
# --------------------------------------------------------------------------- #

def _make_overlay_8085() -> tk.Toplevel:
    top = tk.Toplevel()
    top.attributes("-fullscreen", True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.25)
    top.config(bg="black", cursor="crosshair")
    top.lift()
    return top

def overlay_pick_grid(rows, cols, keys, label_text):
    result = {"pts": {}}
    top = _make_overlay_8085()
    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    canvas.create_text(top.winfo_screenwidth() // 2, 30, text=label_text,
                       fill="white", font=("Segoe UI", 14, "bold"))

    state = {"x0": 0, "y0": 0, "rect": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x_root, e.y_root
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff5555", width=2)

    def on_drag(e):
        if not state["rect"]: return
        cx0 = state["x0"] - top.winfo_rootx()
        cy0 = state["y0"] - top.winfo_rooty()
        canvas.coords(state["rect"], cx0, cy0, e.x, e.y)

    def on_release(e):
        x1, y1 = min(state["x0"], e.x_root), min(state["y0"], e.y_root)
        x2, y2 = max(state["x0"], e.x_root), max(state["y0"], e.y_root)
        if x2 - x1 > 20 and y2 - y1 > 20:
            w = (x2 - x1) / cols
            h = (y2 - y1) / rows
            idx = 0
            for r in range(rows):
                for c in range(cols):
                    if idx < len(keys):
                        cx = int(x1 + (c * w) + (w / 2))
                        cy = int(y1 + (r * h) + (h / 2))
                        result["pts"][keys[idx]] = (cx, cy)
                        idx += 1
        top.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", lambda e: top.destroy())
    top.focus_force()
    top.wait_window()
    return result["pts"]

def overlay_check_calibration(calib):
    if not calib:
        messagebox.showinfo("Empty", "No calibration data to check.")
        return
        
    top = _make_overlay_8085()
    top.attributes("-alpha", 0.5)
    canvas = tk.Canvas(top, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    
    canvas.create_text(top.winfo_screenwidth() // 2, 30, 
                       text="Calibration Check. Press Esc or Click to close.", 
                       fill="white", font=("Segoe UI", 14, "bold"))
                       
    for key, (x, y) in calib.items():
        r = 15
        canvas.create_oval(x-r, y-r, x+r, y+r, outline="cyan", width=2)
        canvas.create_line(x-20, y, x+20, y, fill="cyan", width=1)
        canvas.create_line(x, y-20, x, y+20, fill="cyan", width=1)
        canvas.create_text(x+22, y, text=key, fill="yellow", font=("Segoe UI", 12, "bold"), anchor="w")
        
    top.bind("<Escape>", lambda e: top.destroy())
    top.bind("<Button-1>", lambda e: top.destroy())
    top.focus_force()
    top.wait_window()

class Sim8085Tab(ttk.Frame):
    def __init__(self, parent, root_app):
        super().__init__(parent)
        self.root_app = root_app
        self.calib = {}
        self.stop_flag = threading.Event()
        self.delay_var = tk.DoubleVar(value=0.1)
        
        self._build_ui()
        self.load_data()
        self.save_data()

    def _withdraw_and_restore(self, callback):
        geo = self.root_app.root.geometry()
        self.root_app.root.withdraw()
        try: callback()
        finally:
            self.root_app.root.deiconify()
            self.root_app.root.geometry(geo)
            self.root_app.root.lift()

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=(5, 5, 5, 0))
        top_bar.pack(fill="x")
        ttk.Button(top_bar, text="📂 Browse .txt", command=self.load_from_txt).pack(side="left")
        ttk.Label(top_bar, text="Format: Input: 8000H: ... | Command: 9001H: ...").pack(side="left", padx=5)

        self.stage_notebook = ttk.Notebook(self)
        self.stage_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_input = ttk.Frame(self.stage_notebook)
        self.stage_notebook.add(self.tab_input, text="Input Stage")
        
        self.tab_command = ttk.Frame(self.stage_notebook)
        self.stage_notebook.add(self.tab_command, text="Command Stage")

        self._build_input_stage()
        self._build_command_stage()

    def _build_input_stage(self):
        left = ttk.Frame(self.tab_input, padding=5)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self.tab_input, padding=5)
        right.pack(side="right", fill="y")

        # Settings
        settings = ttk.Frame(left)
        settings.pack(side="bottom", fill="x", pady=2)
        
        ttk.Label(settings, text="Delay:").pack(side="left")
        self.delay_label_in = ttk.Label(settings, text="0.1s", width=4)
        ttk.Scale(settings, from_=0.1, to=2.0, variable=self.delay_var, orient="horizontal", length=80,
                  command=lambda val: self.delay_label_in.config(text=f"{float(val):.1f}s")).pack(side="left", padx=2)
        self.delay_label_in.pack(side="left")
        
        ttk.Label(settings, text="  Start Addr:").pack(side="left")
        self.in_start_addr_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.in_start_addr_var, width=7, font=("Consolas", 9)).pack(side="left", padx=2)

        self.run_in_btn = ttk.Button(left, text="▶ Run Input Stage", command=lambda: self.run_input_stage())
        self.run_in_btn.pack(side="bottom", fill="x", pady=2)

        live = ttk.LabelFrame(left, text="Live Action", padding=2)
        live.pack(side="bottom", fill="x", pady=2)
        self.in_live_status_var = tk.StringVar(value="Idle...")
        ttk.Label(live, textvariable=self.in_live_status_var, font=("Consolas", 11, "bold"), foreground="#4a90e2").pack()

        self.log_var = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.log_var, foreground="#2a8").pack(side="bottom", anchor="w")

        ttk.Label(left, text="Paste full line below:").pack(side="top", anchor="w")
        self.in_code_text = tk.Text(left, height=8, font=("Consolas", 10), bd=1, relief="solid")
        self.in_code_text.pack(side="top", fill="both", expand=True, pady=(2, 5))
        
        self.in_code_text.bind("<KeyRelease>", lambda e: self._on_text_change(self.in_code_text, self.in_start_addr_var))
        self.in_code_text.bind("<<Paste>>", lambda e: self.root_app.root.after(50, lambda: self._on_text_change(self.in_code_text, self.in_start_addr_var)))

        # Calibration Box
        calib = ttk.LabelFrame(right, text="Calibration", padding=5)
        calib.pack(fill="x")
        self.btn_calib_hex = ttk.Button(calib, text="Auto-Cal 0-F", command=self.auto_calib_hex, style="Red.TButton")
        self.btn_calib_hex.pack(fill="x", pady=2)
        self.btn_calib_func = ttk.Button(calib, text="Auto-Cal Funcs", command=self.auto_calib_func, style="Red.TButton")
        self.btn_calib_func.pack(fill="x", pady=2)
        ttk.Button(calib, text="Check Cal", command=self.check_calibration).pack(fill="x", pady=2)

    def _build_command_stage(self):
        left = ttk.Frame(self.tab_command, padding=5)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self.tab_command, padding=5)
        right.pack(side="right", fill="y")

        settings = ttk.Frame(left)
        settings.pack(side="bottom", fill="x", pady=2)
        
        ttk.Label(settings, text="Delay:").pack(side="left")
        self.delay_label_cmd = ttk.Label(settings, text="0.1s", width=4)
        ttk.Scale(settings, from_=0.1, to=2.0, variable=self.delay_var, orient="horizontal", length=80,
                  command=lambda val: self.delay_label_cmd.config(text=f"{float(val):.1f}s")).pack(side="left", padx=2)
        self.delay_label_cmd.pack(side="left")
        
        ttk.Label(settings, text=" Start:").pack(side="left")
        self.cmd_start_addr_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.cmd_start_addr_var, width=7, font=("Consolas", 9)).pack(side="left", padx=2)
        
        ttk.Label(settings, text=" Out:").pack(side="left")
        self.output_addr_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.output_addr_var, width=7, font=("Consolas", 9)).pack(side="left", padx=2)

        self.run_cmd_btn = ttk.Button(left, text="▶ Run Command Stage", command=lambda: self.run_command_stage())
        self.run_cmd_btn.pack(side="bottom", fill="x", pady=2)

        live = ttk.LabelFrame(left, text="Live Action", padding=2)
        live.pack(side="bottom", fill="x", pady=2)
        self.cmd_live_status_var = tk.StringVar(value="Idle...")
        ttk.Label(live, textvariable=self.cmd_live_status_var, font=("Consolas", 11, "bold"), foreground="#4a90e2").pack()

        self.cmd_log_var = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.cmd_log_var, foreground="#2a8").pack(side="bottom", anchor="w")

        ttk.Label(left, text="Paste full line below:").pack(side="top", anchor="w")
        self.cmd_code_text = tk.Text(left, height=8, font=("Consolas", 10), bd=1, relief="solid")
        self.cmd_code_text.pack(side="top", fill="both", expand=True, pady=(2, 5))
        
        self.cmd_code_text.bind("<KeyRelease>", lambda e: self._on_text_change(self.cmd_code_text, self.cmd_start_addr_var))
        self.cmd_code_text.bind("<<Paste>>", lambda e: self.root_app.root.after(50, lambda: self._on_text_change(self.cmd_code_text, self.cmd_start_addr_var)))

        calib = ttk.LabelFrame(right, text="Calibration (Shared)", padding=5)
        calib.pack(fill="x")
        ttk.Label(calib, text="Uses the same calibration\nas the Input Stage.").pack(pady=10)

    def update_theme(self, c):
        self.in_code_text.config(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["fg"])
        self.cmd_code_text.config(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["fg"])
        self.in_code_text.tag_configure("highlight", background=c["highlight"], foreground=c["highlight_fg"], font=("Consolas", 10, "bold"))
        self.cmd_code_text.tag_configure("highlight", background=c["highlight"], foreground=c["highlight_fg"], font=("Consolas", 10, "bold"))

    def _on_text_change(self, text_widget, addr_var):
        text = text_widget.get("1.0", "end").strip()
        if ":" in text:
            addr = re.sub(r'[^0-9A-Fa-f]', '', text.split(":")[0])
            if addr: addr_var.set(addr.upper())

    def load_from_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")], parent=self.root_app.root)
        if not path: return
        try:
            with open(path, "r") as f: content = f.read()
            match = re.search(r'Input:\s*(.*?)(?=Command:|Output:|$)', content, re.DOTALL | re.IGNORECASE)
            if match:
                self.in_code_text.delete("1.0", "end")
                self.in_code_text.insert("1.0", match.group(1).strip())
                self._on_text_change(self.in_code_text, self.in_start_addr_var)
            
            match = re.search(r'Command:\s*(.*?)(?=Output:|$)', content, re.DOTALL | re.IGNORECASE)
            if match:
                self.cmd_code_text.delete("1.0", "end")
                self.cmd_code_text.insert("1.0", match.group(1).strip())
                self._on_text_change(self.cmd_code_text, self.cmd_start_addr_var)
                
            match = re.search(r'Output:\s*([0-9A-Fa-f]+)', content, re.IGNORECASE)
            if match: self.output_addr_var.set(match.group(1).upper())
                
            messagebox.showinfo("Success", "Data loaded successfully.", parent=self.root_app.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}", parent=self.root_app.root)

    def load_data(self):
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, "r") as f: self.calib = json.load(f)
            except: pass
        self.update_calib_ui()

    def save_data(self):
        try:
            with open(CALIBRATION_FILE, "w") as f: json.dump(self.calib, f, indent=2)
        except: pass

    def update_calib_ui(self):
        if "0" in self.calib: self.btn_calib_hex.config(text="Hex Calibrated ✓", style="Green.TButton")
        else: self.btn_calib_hex.config(text="Auto-Cal 0-F", style="Red.TButton")

        if "Exec" in self.calib: self.btn_calib_func.config(text="Funcs Calibrated ✓", style="Green.TButton")
        else: self.btn_calib_func.config(text="Auto-Cal Funcs", style="Red.TButton")

    def auto_calib_hex(self):
        keys = ["C", "D", "E", "F", "8", "9", "A", "B", "4", "5", "6", "7", "0", "1", "2", "3"]
        def task():
            pts = overlay_pick_grid(4, 4, keys, "Drag a box around the 16 HEX KEYS. Esc to cancel.")
            if pts:
                self.calib.update(pts)
                self.save_data()
                self.update_calib_ui()
        self._withdraw_and_restore(task)

    def auto_calib_func(self):
        keys = ["Reset", "Kbint", "Prev", "exm Mem", "Next", "exm Reg", "Go", "Exec"]
        def task():
            pts = overlay_pick_grid(4, 2, keys, "Drag a box around the 8 FUNCTIONS. Esc to cancel.")
            if pts:
                self.calib.update(pts)
                self.save_data()
                self.update_calib_ui()
        self._withdraw_and_restore(task)

    def check_calibration(self):
        self._withdraw_and_restore(lambda: overlay_check_calibration(self.calib))

    def _click_hex(self, hex_string, prefix=""):
        for char in hex_string.upper():
            if self.stop_flag.is_set(): return
            self.root_app.root.after(0, lambda c=char, p=prefix: self._update_live_status(f"➔ {p} Typing: {c}"))
            if char in self.calib:
                pyautogui.click(*self.calib[char])
                time.sleep(self.delay_var.get()) 
            else:
                raise ValueError(f"Key '{char}' is not calibrated!")

    def _click_btn(self, key_name):
        if self.stop_flag.is_set(): return
        self.root_app.root.after(0, lambda k=key_name: self._update_live_status(f"➔ Clicking: {k}"))
        if key_name in self.calib:
            pyautogui.click(*self.calib[key_name])
            time.sleep(self.delay_var.get())
        else:
            raise ValueError(f"Button '{key_name}' is not calibrated!")

    def _update_live_status(self, msg):
        if self.stage_notebook.index(self.stage_notebook.select()) == 0: self.in_live_status_var.set(msg)
        else: self.cmd_live_status_var.set(msg)

    def _parse_combined_input(self, text, current_addr_var):
        text = text.strip()
        if not text: return None, []
        addr = current_addr_var.get().strip().upper().replace("H", "")
        code_part = text

        if ":" in text:
            parts = text.split(":", 1)
            addr_clean = re.sub(r'[^0-9A-F]', '', parts[0].upper())
            if addr_clean:
                addr = addr_clean
                current_addr_var.set(addr)
            code_part = parts[1]

        byte_clean = re.sub(r'[^0-9A-F]', '', code_part.upper())
        bytes_list = [byte_clean[i:i+2] for i in range(0, len(byte_clean), 2)]

        if not addr:
            addr = simpledialog.askstring("Address Required", "Please enter Starting Address:", parent=self.root_app.root)
            if not addr: return None, []
            addr = addr.strip().upper().replace("H", "")
            current_addr_var.set(addr)

        return addr, bytes_list

    def _highlight_current_byte(self, text_widget, byte_val, search_start_var):
        if search_start_var[0] is None:
            colon_pos = text_widget.search(":", "1.0", stopindex="end")
            search_start_var[0] = f"{colon_pos}+1c" if colon_pos else "1.0"
            
        pos = text_widget.search(byte_val, search_start_var[0], stopindex="end")
        if pos:
            end_pos = f"{pos}+{len(byte_val)}c"
            text_widget.tag_remove("highlight", "1.0", "end")
            text_widget.tag_add("highlight", pos, end_pos)
            text_widget.see(pos)
            search_start_var[0] = end_pos

    def run_input_stage(self, is_pipeline=False, callback=None):
        if "0" not in self.calib or "Exec" not in self.calib:
            messagebox.showerror("Calibration Missing", "Please calibrate first.", parent=self.root_app.root)
            if callback: callback(False)
            return

        code_input = self.in_code_text.get("1.0", "end").strip()
        if not code_input:
            messagebox.showinfo("No Code", "Please paste opcodes.", parent=self.root_app.root)
            if callback: callback(False)
            return

        start_addr, bytes_list = self._parse_combined_input(code_input, self.in_start_addr_var)
        if start_addr is None or not bytes_list: 
            if callback: callback(False)
            return

        self.stop_flag.clear()
        self.run_in_btn.config(state="disabled")
        self.log_var.set("Running...")
        self.in_live_status_var.set("➔ Starting...")
        threading.Thread(target=self._input_stage_thread, args=(start_addr, bytes_list, callback), daemon=True).start()

    def _input_stage_thread(self, start_addr, bytes_list, callback=None):
        success = False
        try:
            time.sleep(0.5)
            self._click_btn("Reset")
            self._click_btn("exm Mem")
            self._click_hex(start_addr, prefix="Address:")
            self._click_btn("Next")

            search_start = [None]
            for i, byte in enumerate(bytes_list):
                if self.stop_flag.is_set(): break
                self.root_app.root.after(0, lambda b=byte: self._highlight_current_byte(self.in_code_text, b, search_start))
                self._click_hex(byte, prefix=f"Data ({i+1}/{len(bytes_list)}):")
                self._click_btn("Next")

            success = not self.stop_flag.is_set()
            if success: self.root_app.root.after(0, lambda: self._run_finished(self.run_in_btn, self.log_var, self.in_live_status_var, True, "Input Executed!"))
            else: self.root_app.root.after(0, lambda: self._run_finished(self.run_in_btn, self.log_var, self.in_live_status_var, False, "Stopped."))
            
        except Exception as e:
            self.root_app.root.after(0, lambda: self._run_finished(self.run_in_btn, self.log_var, self.in_live_status_var, False, str(e)))
        finally:
            self.root_app.root.after(0, lambda: self.in_code_text.tag_remove("highlight", "1.0", "end"))
            if callback: self.root_app.root.after(0, lambda: callback(success))

    def run_command_stage(self, is_pipeline=False, callback=None):
        if "0" not in self.calib or "Exec" not in self.calib:
            messagebox.showerror("Calibration Missing", "Please calibrate first.", parent=self.root_app.root)
            if callback: callback(False)
            return

        code_input = self.cmd_code_text.get("1.0", "end").strip()
        if not code_input:
            messagebox.showinfo("No Code", "Please paste opcodes.", parent=self.root_app.root)
            if callback: callback(False)
            return

        start_addr, bytes_list = self._parse_combined_input(code_input, self.cmd_start_addr_var)
        if start_addr is None or not bytes_list: 
            if callback: callback(False)
            return

        out_addr = self.output_addr_var.get().strip().upper().replace("H", "")

        self.stop_flag.clear()
        self.run_cmd_btn.config(state="disabled")
        self.cmd_log_var.set("Running...")
        self.cmd_live_status_var.set("➔ Starting...")
        threading.Thread(target=self._command_stage_thread, args=(start_addr, bytes_list, out_addr, callback), daemon=True).start()

    def _command_stage_thread(self, start_addr, bytes_list, out_addr, callback=None):
        success = False
        try:
            time.sleep(0.5)
            self._click_btn("Reset")
            self._click_btn("exm Mem")
            self._click_hex(start_addr, prefix="Address:")
            self._click_btn("Next")

            found_hlt = False
            search_start = [None]
            for i, byte in enumerate(bytes_list):
                if self.stop_flag.is_set(): break
                self.root_app.root.after(0, lambda b=byte: self._highlight_current_byte(self.cmd_code_text, b, search_start))
                self._click_hex(byte, prefix=f"Data ({i+1}/{len(bytes_list)}):")
                
                if byte.upper() == "76":
                    found_hlt = True
                    self.root_app.root.after(0, lambda: self.cmd_live_status_var.set("➔ Found HLT! Executing..."))
                    time.sleep(self.delay_var.get() * 2)
                    self._click_btn("Next") 
                    self._click_btn("Go")
                    self._click_hex(start_addr, prefix="Exec Addr:")
                    self._click_btn("Exec")
                    break 
                self._click_btn("Next")

            if found_hlt and out_addr and not self.stop_flag.is_set():
                self.root_app.root.after(0, lambda: self.cmd_live_status_var.set("➔ Checking Output..."))
                time.sleep(1)
                self._click_btn("Reset")
                self._click_btn("exm Mem")
                self._click_hex(out_addr, prefix="Output Addr:")
                self._click_btn("Next")

            success = not self.stop_flag.is_set() and found_hlt
            if success: self.root_app.root.after(0, lambda: self._run_finished(self.run_cmd_btn, self.cmd_log_var, self.cmd_live_status_var, True, "Command Executed!"))
            elif not found_hlt: self.root_app.root.after(0, lambda: self._run_finished(self.run_cmd_btn, self.cmd_log_var, self.cmd_live_status_var, False, "No HLT (76) found."))
            else: self.root_app.root.after(0, lambda: self._run_finished(self.run_cmd_btn, self.cmd_log_var, self.cmd_live_status_var, False, "Stopped."))
            
        except Exception as e:
            self.root_app.root.after(0, lambda: self._run_finished(self.run_cmd_btn, self.cmd_log_var, self.cmd_live_status_var, False, str(e)))
        finally:
            self.root_app.root.after(0, lambda: self.cmd_code_text.tag_remove("highlight", "1.0", "end"))
            if callback: self.root_app.root.after(0, lambda: callback(success))

    def _run_finished(self, btn, log_var, live_var, success, message):
        btn.config(state="normal")
        log_var.set(message)
        if success: live_var.set("Finished Successfully")
        else:
            live_var.set(f"Error: {message}")
            messagebox.showerror("Automation Error", message, parent=self.root_app.root)

# --------------------------------------------------------------------------- #
# Main App Wrapper
# --------------------------------------------------------------------------- #

class WorkflowApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Automation Suite")
        self.root.geometry("950x650")
        self.root.minsize(850, 550)

        self.stop_flag = threading.Event()
        self.pipeline_queue = []
        self.shared_folder_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        
        self.pipe_in_var = tk.BooleanVar(value=True)
        self.pipe_cmd_var = tk.BooleanVar(value=True)
        self.pipe_ss_var = tk.BooleanVar(value=True)

        # Load settings
        self.current_theme = "light"
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.current_theme = data.get("theme", "light")
            except: pass

        self._build_ui()
        self.apply_theme(self.current_theme)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if keyboard:
            try: keyboard.add_hotkey('ctrl+shift+q', self._brute_force_stop)
            except Exception: pass

    def _brute_force_stop(self):
        self.stop_flag.set()
        self.tab_workflow.stop_flag.set()
        self.tab_8085.stop_flag.set()
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.root.after(0, self.root.focus_force)

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        c = apply_theme(self.root, theme_name)
        self.tab_workflow.update_theme(c)
        self.tab_8085.update_theme(c)
        
        # Update FAB
        self.fab.config(bg=c["fab_bg"], fg=c["fab_fg"], activebackground=c["select_bg"], activeforeground=c["select_fg"])
        
        # Update FAB Menu
        self.pipeline_menu.config(bg=c["field_bg"], fg=c["field_fg"], 
                                  activebackground=c["select_bg"], activeforeground=c["select_fg"])
        
        # Save Setting
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"theme": theme_name}, f)
        except: pass

    def _build_ui(self):
        # --- Top Bar ---
        top_bar = ttk.Frame(self.root, padding=(5, 5, 5, 0))
        top_bar.pack(fill="x", side="top")
        
        ttk.Label(top_bar, text="Output Folder:").pack(side="left")
        ttk.Entry(top_bar, textvariable=self.shared_folder_var).pack(side="left", fill="x", expand=True, padx=4)
        
        def browse_folder():
            d = filedialog.askdirectory(initialdir=self.shared_folder_var.get() or BASE_DIR, parent=self.root)
            if d: self.shared_folder_var.set(d)
                
        ttk.Button(top_bar, text="Browse", command=browse_folder).pack(side="left", padx=2)
        ttk.Button(top_bar, text="Open", command=self.open_shared_folder).pack(side="left", padx=2)

        # Theme Switcher
        theme_frame = ttk.Frame(top_bar)
        theme_frame.pack(side="right", padx=5)
        ttk.Label(theme_frame, text="Theme:").pack(side="left", padx=(0, 2))
        self.theme_var = tk.StringVar(value=self.current_theme)
        theme_cb = ttk.Combobox(theme_frame, textvariable=self.theme_var, values=["light", "dark", "hacker"], state="readonly", width=6)
        theme_cb.pack(side="left")
        theme_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_theme(self.theme_var.get()))

        # --- Notebook ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_workflow = ScreenWorkflowTab(self.notebook, self)
        self.notebook.add(self.tab_workflow, text="Screenshot Workflow")
        
        self.tab_8085 = Sim8085Tab(self.notebook, self)
        self.notebook.add(self.tab_8085, text="8085 Simulator")

        # --- Status Bar & FAB ---
        status_bar = ttk.Frame(self.root, padding=(5, 2))
        status_bar.pack(side="bottom", fill="x")
        ttk.Label(status_bar, text=f"Data: {WORKFLOW_FILE}", foreground="#888", font=("Segoe UI", 8)).pack(side="left")
        
        # FAB Menu
        self.pipeline_menu = tk.Menu(self.root, tearoff=0)
        self.pipeline_menu.add_checkbutton(label="1. Input Stage", variable=self.pipe_in_var)
        self.pipeline_menu.add_checkbutton(label="2. Command Stage", variable=self.pipe_cmd_var)
        self.pipeline_menu.add_checkbutton(label="3. Screenshot Workflow", variable=self.pipe_ss_var)
        
        # The Floating Action Button
        self.fab = tk.Button(self.root, text="▶ Run Pipeline", font=("Segoe UI", 9, "bold"), relief="flat", bd=0, padx=10, pady=4)
        self.fab.place(relx=0.98, rely=0.96, anchor="se") # Bottom Right
        self.fab.bind("<Button-1>", lambda e: self.run_pipeline())
        self.fab.bind("<Button-3>", self.show_pipeline_menu)

        self.pipeline_status_var = tk.StringVar(value="Idle")
        self.pipeline_status_lbl = ttk.Label(self.root, textvariable=self.pipeline_status_var, font=("Segoe UI", 9, "bold"))
        self.pipeline_status_lbl.place(relx=0.80, rely=0.96, anchor="se") # Placed to the left of the button

    def show_pipeline_menu(self, event):
        try:
            self.pipeline_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.pipeline_menu.grab_release()

    def open_shared_folder(self):
        path = self.shared_folder_var.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showinfo("Folder not found", "The folder doesn't exist yet.", parent=self.root)
            return
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": os.system(f'open "{path}"')
            else: os.system(f'xdg-open "{path}"')
        except Exception as e:
            messagebox.showerror("Cannot open folder", str(e), parent=self.root)

    def run_pipeline(self):
        self.pipeline_queue = []
        if self.pipe_in_var.get(): self.pipeline_queue.append(("Input Stage", self.tab_8085.run_input_stage, 1, 0))
        if self.pipe_cmd_var.get(): self.pipeline_queue.append(("Command Stage", self.tab_8085.run_command_stage, 1, 1))
        if self.pipe_ss_var.get(): self.pipeline_queue.append(("Screenshot Workflow", self.tab_workflow.run_workflow, 0, 0))

        if not self.pipeline_queue:
            messagebox.showinfo("Empty Pipeline", "Please right-click the pipeline button and check at least one stage.", parent=self.root)
            return

        self.fab.config(state="disabled")
        self._next_pipeline_step()

    def _next_pipeline_step(self):
        if not self.pipeline_queue:
            self.pipeline_status_var.set("Finished")
            self.fab.config(state="normal")
            return
            
        name, func, main_idx, sub_idx = self.pipeline_queue.pop(0)
        self.pipeline_status_var.set(f"➔ {name}")
        
        self.notebook.select(main_idx)
        if main_idx == 1: self.tab_8085.stage_notebook.select(sub_idx)
            
        func(is_pipeline=True, callback=self._on_pipeline_step_done)

    def _on_pipeline_step_done(self, success):
        if success:
            self._next_pipeline_step()
        else:
            self.pipeline_status_var.set("Stopped/Failed")
            self.fab.config(state="normal")

    def _on_close(self):
        self.stop_flag.set()
        self.tab_workflow.stop_flag.set()
        self.tab_8085.stop_flag.set()
        self.tab_workflow.save_workflow()
        self.root.destroy()

    def run(self): 
        self.root.mainloop()

if __name__ == "__main__":
    WorkflowApp().run()