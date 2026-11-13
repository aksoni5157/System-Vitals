"""
================================================================================
 SisVi+ — System Vitals AI  |  VITA AI Edition
 File: app.py
================================================================================
 System health dashboard + VITA AI assistant
 + Security Shield + Optimizer + Gesture HUD

 Team Vitals:
    Leader : Akash Soni
    Members: Ansh Jangid, Abhinav Pratap Singh, Ansh Porwal, Anmol Tanwar
    Supervisor: Dr. Vishal Srivastava

 Run:  python app.py
================================================================================
"""

import os, sys, json, math, time, logging, platform, threading, random, ctypes, queue
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import customtkinter as ctk
except ImportError as e:
    raise ImportError("pip install customtkinter") from e
try:
    from PIL import Image, ImageTk
except ImportError as e:
    raise ImportError("pip install Pillow") from e

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database_manager import DatabaseManager
from telemetry_engine import TelemetryEngine
from ai_brain import AIBrain, Diagnosis
from chat_adapter import HybridChatEngine

from security_shield import SecurityShield
from optimizer_engine import OptimizerEngine

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("SisVi+")
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

# ── JARVIS palette ────────────────────────────────────────────────────
BG="#080D16"; PNL="#101925"; CY="#65E6C2"; GD="#F5B95F"; RD="#FF6B77"
GR="#65DDAA"; TX="#E8EEF7"; TX2="#A5B3C5"; DM="#728198"; BD="#26364A"
BTN="#172538"; BTH="#20364F"; BAR="#19283A"; PK="#A994FF"
FONT="Segoe UI"; TICK=1000; BRKM=45.0

ASSETS=os.path.join(PROJECT_ROOT,"assets")
AVATAR=os.path.join(ASSETS,"anime_assistant.jpg")
SPLASH=os.path.join(ASSETS,"splash_wave.jpg")
ICON=os.path.join(ASSETS,"sisvi_plus.ico")


class HoverTooltip:
    """Small native tooltip shown after a brief taskbar hover."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self.pending = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _schedule(self, _event=None):
        self.pending = self.widget.after(450, self._show)

    def _show(self):
        if self.window or not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=PNL)
        label = tk.Label(self.window, text=self.text, bg=PNL, fg=TX,
                         font=(FONT, 9), padx=10, pady=6,
                         relief="solid", bd=1)
        label.pack()
        x = self.widget.winfo_rootx() + (self.widget.winfo_width() - label.winfo_reqwidth()) // 2
        y = self.widget.winfo_rooty() - label.winfo_reqheight() - 8
        self.window.geometry(f"+{max(4, x)}+{max(4, y)}")

    def _hide(self, _event=None):
        if self.pending:
            try:
                self.widget.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None
        if self.window:
            self.window.destroy()
            self.window = None


class TaskbarButton(ctk.CTkButton):
    """Compact taskbar button with a short color transition on hover."""

    def __init__(self, *args, tooltip="", base_color=BTN, hover_color=BTH, **kwargs):
        self._base_color = base_color
        self._hover_color = hover_color
        self._color_step = 0
        self._color_target = 0
        self._color_after = None
        super().__init__(*args, fg_color=base_color, hover=False, **kwargs)
        self.bind("<Enter>", lambda _e: self._animate_to(1), add="+")
        self.bind("<Leave>", lambda _e: self._animate_to(0), add="+")
        if tooltip:
            HoverTooltip(self, tooltip)

    @staticmethod
    def _blend(start, end, amount):
        a = tuple(int(start[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(end[i:i + 2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))

    def _animate_to(self, target):
        self._color_target = target
        if self._color_after:
            try:
                self.after_cancel(self._color_after)
            except tk.TclError:
                pass
        self._animate_step()

    def _animate_step(self):
        delta = 1 if self._color_target else -1
        self._color_step = max(0, min(5, self._color_step + delta))
        color = self._blend(self._base_color, self._hover_color, self._color_step / 5)
        self.configure(fg_color=color)
        if self._color_step != (5 if self._color_target else 0):
            self._color_after = self.after(18, self._animate_step)
        else:
            self._color_after = None


# ######################################################################
#  CINEMATIC SPLASH
# ######################################################################
class CinematicSplash(ctk.CTkToplevel):
    def __init__(self, master, on_done):
        super().__init__(master); self._done=on_done
        self.overrideredirect(True); self.configure(fg_color="#000000")
        w,h=700,500
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")
        self.attributes("-topmost",True)
        try:
            if os.path.exists(ICON): self.after(50,lambda:self.iconbitmap(ICON))
        except: pass
        self.grid_rowconfigure((0,1,2,3,4,5,6),weight=1); self.grid_columnconfigure(0,weight=1)

        # Splash image
        try:
            pil=Image.open(SPLASH).resize((200,265))
            self._si=ctk.CTkImage(light_image=pil,dark_image=pil,size=(200,265))
            self._if=ctk.CTkFrame(self,fg_color="transparent"); self._if.grid(row=0,column=0,pady=(20,0))
            ctk.CTkLabel(self._if,image=self._si,text="").pack()
        except: self._if=None

        self._tv=tk.StringVar(value="")
        self._tl=ctk.CTkLabel(self,textvariable=self._tv,
            font=ctk.CTkFont(family=FONT,size=36,weight="bold"),text_color=CY)
        self._tl.grid(row=2,column=0)
        self._sv=tk.StringVar(value="")
        ctk.CTkLabel(self,textvariable=self._sv,
            font=ctk.CTkFont(family=FONT,size=13),text_color=GD).grid(row=3,column=0,pady=(0,6))
        self._stv=tk.StringVar(value="")
        ctk.CTkLabel(self,textvariable=self._stv,
            font=ctk.CTkFont(family=FONT,size=10),text_color="#4A6FA5").grid(row=4,column=0,pady=(0,6))
        self._pb=ctk.CTkProgressBar(self,height=3,corner_radius=0,width=400,
                                     progress_color=CY,fg_color="#111")
        self._pb.grid(row=5,column=0,pady=(0,25)); self._pb.set(0)
        self._tt="S I S V I +"; self._ti=0; self._pv=0.0; self._bs=0
        self.after(300,self._go)

    def _go(self):
        self._bounce(); self.after(200,self._type)

    def _bounce(self):
        if not self.winfo_exists(): return
        self._bs+=1
        if self._if:
            o=int(5*math.sin(self._bs*0.15))
            self._if.grid(row=0,column=0,pady=(20+o,max(0,-o)))
        if self._bs<60: self.after(33,self._bounce)

    def _type(self):
        if not self.winfo_exists(): return
        if self._ti<=len(self._tt):
            self._tv.set(self._tt[:self._ti]); self._ti+=1; self.after(90,self._type)
        else: self.after(150,self._flash,0)

    def _flash(self,s):
        if not self.winfo_exists(): return
        cs=["#FFFFFF",CY,"#FFFFFF",CY]
        if s<len(cs):
            self._tl.configure(text_color=cs[s]); self.after(80,self._flash,s+1)
        else:
            self._tl.configure(text_color=CY)
            self._sv.set('"One AI. Two Lives. Your Device & Your Digital Wellbeing."')
            self._stv.set("Initializing systems...")
            self.after(300,self._prog)

    def _prog(self):
        if not self.winfo_exists(): return
        self._pv+=0.028; self._pb.set(min(1.0,self._pv))
        if .2<self._pv<.23: self._stv.set("Loading telemetry engine...")
        elif .4<self._pv<.43: self._stv.set("Activating security shield...")
        elif .6<self._pv<.63: self._stv.set("Calibrating AI brain...")
        elif .8<self._pv<.83: self._stv.set("VITA AI is getting ready")
        elif .95<self._pv: self._stv.set("All systems online. ✦")
        if self._pv<1.0: self.after(40,self._prog)
        else: self.after(500,self._fin)

    def _fin(self):
        if self.winfo_exists(): self._done(); self.destroy()


# ######################################################################
#  MAIN DASHBOARD
# ######################################################################
class SystemVitalsDashboard(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("SisVi+ | VITA AI")
        self.geometry("1480x920"); self.minsize(1180,760)
        self.configure(fg_color=BG)
        self.after(0, self._enable_windows_backdrop)
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        try:
            if os.path.exists(ICON): self.iconbitmap(ICON)
        except: pass

        # ── Backends ──
        dbp=os.path.join(PROJECT_ROOT,"vitals_ecosystem.db")
        self.db=DatabaseManager(dbp)
        self.ai=AIBrain()
        self.chat=HybridChatEngine()
        self.security=SecurityShield(db_manager=self.db)
        self.optimizer=OptimizerEngine(db_manager=self.db)

        self._lock=threading.Lock(); self._snap=None
        self.telem=TelemetryEngine(
            db_manager=self.db, sample_interval_sec=2.0,
            write_interval_sec=15.0, on_sample=self._on_sample)

        # State
        self._brk_ign=0; self._brk_last=0.0
        self._sess_id=self.db.start_session_log("focus")
        self._diag=None; self._ui_ms=TICK; self._db_last=0.0

        # Avatar
        self._avatar=None
        try:
            if os.path.exists(AVATAR):
                p=Image.open(AVATAR).resize((80,80))
                self._avatar=ctk.CTkImage(light_image=p,dark_image=p,size=(80,80))
        except: pass

        self._build_layout()
        self.withdraw()
        self._splash=CinematicSplash(self, on_done=self._after_splash)

    def _enable_windows_backdrop(self):
        """Ask Windows 11 for its native Mica backdrop; older systems ignore it."""
        if platform.system() != "Windows":
            return
        try:
            hwnd = self.winfo_id()
            backdrop_type = ctypes.c_int(2)  # DWMSBT_MAINWINDOW
            dark_titlebar = ctypes.c_int(1)  # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(dark_titlebar), ctypes.sizeof(dark_titlebar))
            self.attributes("-alpha", 0.985)
        except Exception as exc:
            logger.debug(f"Native Windows backdrop unavailable: {exc}")

    def _after_splash(self):
        self.deiconify()
        self.telem.start()
        self.after(self._ui_ms, self._tick)
        # Show mode status
        if self.chat.is_online:
            self._bot_msg("🟢 ChatGPT connected! Ask me anything~! 🌸♡")
        else:
            self._bot_msg("VITA AI uses a local Qwen3 model for generative chat.\n\n"
                          "Chat requests stay on this computer. If the model or local "
                          "Ollama service is unavailable, the status and reply will say so.")

    def _on_sample(self, s):
        with self._lock: self._snap=s

    def _get_snap_safe(self):
        with self._lock: return dict(self._snap) if self._snap else None

    # ==================================================================
    # LAYOUT
    # ==================================================================
    def _build_layout(self):
        self.grid_rowconfigure(1,weight=1)
        self.grid_rowconfigure(2,weight=0,minsize=76)
        self.grid_columnconfigure(0,weight=1)
        self._build_header()
        self._build_body()
        self._build_taskbar()

    # ── HEADER ──
    def _build_header(self):
        h=ctk.CTkFrame(self,corner_radius=0,fg_color=BG,height=82)
        h.grid(row=0,column=0,sticky="ew"); h.grid_columnconfigure(0,weight=1)
        lf=ctk.CTkFrame(h,fg_color="transparent")
        lf.grid(row=0,column=0,sticky="w",padx=28,pady=13)
        ctk.CTkLabel(lf, text="◈  S I S V I +",
            font=ctk.CTkFont(family=FONT,size=25,weight="bold"),
            text_color=CY).pack(anchor="w")
        ctk.CTkLabel(lf, text="VITA AI  |  System health • Wellbeing • Assistant",
            font=ctk.CTkFont(family=FONT,size=11),text_color=TX2).pack(anchor="w",pady=(3,0))
        self._clk=tk.StringVar(value="")
        ctk.CTkLabel(h,textvariable=self._clk,
            font=ctk.CTkFont(family=FONT,size=11,weight="bold"),text_color=TX2
            ).grid(row=0,column=1,sticky="e",padx=28)
        self._updclk()

    def _updclk(self):
        now = datetime.now()
        self._clk.set(now.strftime("%H:%M:%S  |  %d %b %Y"))
        if hasattr(self, "_taskbar_clock_text"):
            self._taskbar_clock_text.set(now.strftime("%I:%M %p\n%d %b"))
        self.after(1000,self._updclk)

    # ── BODY ──
    def _build_body(self):
        b=ctk.CTkFrame(self,corner_radius=0,fg_color="transparent")
        b.grid(row=1,column=0,sticky="nsew",padx=20,pady=(4,12))
        b.grid_rowconfigure(0,weight=1)
        b.grid_columnconfigure(0,weight=11,uniform="dashboard")
        b.grid_columnconfigure(1,weight=10,uniform="dashboard")
        b.grid_columnconfigure(2,weight=13,uniform="dashboard")
        self._build_left(b)
        self._build_center(b)
        self._build_right(b)

    # ── LEFT: Device Health + Security ──
    def _build_left(self,p):
        f=ctk.CTkFrame(p,corner_radius=16,fg_color=PNL,border_width=1,border_color=BD)
        f.grid(row=0,column=0,sticky="nsew",padx=(0,4)); f.grid_columnconfigure(0,weight=1)

        ctk.CTkLabel(f,text="◈ DEVICE HEALTH",
            font=ctk.CTkFont(family=FONT,size=13,weight="bold"),
            text_color=CY).grid(row=0,column=0,sticky="w",padx=16,pady=(12,4))
        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=1,column=0,sticky="ew",padx=14,pady=(0,6))

        self.cpu_v,self.cpu_b = self._met(f,2,"CPU LOAD",CY)
        self.ram_v,self.ram_b = self._met(f,4,"RAM USAGE",CY)
        self.sto_v,self.sto_b = self._met(f,6,"DISK USED",CY)
        self.bat_v,self.bat_b = self._met(f,8,"BATTERY SoH",GD)
        self.bat_c=ctk.CTkLabel(f,text="▸ Charge: N/A",
            font=ctk.CTkFont(family=FONT,size=9),text_color=TX2)
        self.bat_c.grid(row=10,column=0,sticky="w",padx=16,pady=(0,4))

        # Security status section
        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=11,column=0,sticky="ew",padx=14,pady=(6,4))
        ctk.CTkLabel(f,text="◈ SECURITY SHIELD",
            font=ctk.CTkFont(family=FONT,size=11,weight="bold"),
            text_color=GD).grid(row=12,column=0,sticky="w",padx=16,pady=(2,4))
        self.sec_st=ctk.CTkLabel(f,text="● PROTECTED",
            font=ctk.CTkFont(family=FONT,size=11,weight="bold"),
            fg_color="#0D3320",corner_radius=6,text_color=GR,padx=10,pady=3)
        self.sec_st.grid(row=13,column=0,sticky="w",padx=16,pady=(0,4))
        self.sec_info=ctk.CTkLabel(f,text="Shield active • 0 threats",
            font=ctk.CTkFont(family=FONT,size=9),text_color=DM)
        self.sec_info.grid(row=14,column=0,sticky="w",padx=16,pady=(0,12))

    def _met(self,p,row,label,accent):
        """Create a metric row with label, value, and progress bar."""
        rf=ctk.CTkFrame(p,fg_color="transparent")
        rf.grid(row=row,column=0,sticky="ew",padx=16,pady=(1,0))
        rf.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(rf,text=f"▸ {label}",
            font=ctk.CTkFont(family=FONT,size=10),text_color=TX2
            ).grid(row=0,column=0,sticky="w")
        vl=ctk.CTkLabel(rf,text="—",
            font=ctk.CTkFont(family=FONT,size=11,weight="bold"),text_color=accent)
        vl.grid(row=0,column=1,sticky="e")
        bar=ctk.CTkProgressBar(p,height=5,corner_radius=2,
            progress_color=accent,fg_color=BAR)
        bar.grid(row=row+1,column=0,sticky="ew",padx=16,pady=(2,6)); bar.set(0)
        return vl,bar

    # ── CENTER: Wellbeing ──
    def _build_center(self,p):
        f=ctk.CTkFrame(p,corner_radius=16,fg_color=PNL,border_width=1,border_color=BD)
        f.grid(row=0,column=1,sticky="nsew",padx=4); f.grid_columnconfigure(0,weight=1)

        ctk.CTkLabel(f,text="◈ DIGITAL WELLBEING",
            font=ctk.CTkFont(family=FONT,size=13,weight="bold"),
            text_color=GD).grid(row=0,column=0,sticky="w",padx=16,pady=(12,4))
        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=1,column=0,sticky="ew",padx=14,pady=(0,6))

        ctk.CTkLabel(f,text="ACTIVE SESSION",
            font=ctk.CTkFont(family=FONT,size=9),text_color=DM
            ).grid(row=2,column=0,sticky="w",padx=16)
        self.sess_l=ctk.CTkLabel(f,text="00:00",
            font=ctk.CTkFont(family=FONT,size=38,weight="bold"),text_color=CY)
        self.sess_l.grid(row=3,column=0,sticky="w",padx=16,pady=(0,8))
        self.focus_b=ctk.CTkLabel(f,text="● FOCUSED",
            font=ctk.CTkFont(family=FONT,size=10,weight="bold"),
            fg_color="#0D3320",corner_radius=6,text_color=GR,padx=10,pady=3)
        self.focus_b.grid(row=4,column=0,sticky="w",padx=16,pady=(0,10))

        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=5,column=0,sticky="ew",padx=14,pady=(0,6))
        ctk.CTkLabel(f,text="NEXT BREAK IN",
            font=ctk.CTkFont(family=FONT,size=9),text_color=DM
            ).grid(row=6,column=0,sticky="w",padx=16)
        self.brk_l=ctk.CTkLabel(f,text="45:00",
            font=ctk.CTkFont(family=FONT,size=22,weight="bold"),text_color=GD)
        self.brk_l.grid(row=7,column=0,sticky="w",padx=16,pady=(0,6))
        self.brk_pb=ctk.CTkProgressBar(f,height=4,corner_radius=2,
            progress_color=GD,fg_color=BAR)
        self.brk_pb.grid(row=8,column=0,sticky="ew",padx=16,pady=(0,8)); self.brk_pb.set(0)

        ctk.CTkButton(f,text="▸ BREAK TAKEN",command=self._manual_break,
            fg_color=BTN,hover_color=BTH,text_color=GD,border_width=1,border_color=GD,
            font=ctk.CTkFont(family=FONT,size=9,weight="bold"),
            corner_radius=6,height=28).grid(row=9,column=0,sticky="ew",padx=16,pady=(0,6))
        self.ign_l=ctk.CTkLabel(f,text="Overridden: 0",
            font=ctk.CTkFont(family=FONT,size=8),text_color=DM)
        self.ign_l.grid(row=10,column=0,sticky="w",padx=16,pady=(0,6))

        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=11,column=0,sticky="ew",padx=14,pady=(0,6))
        ctk.CTkLabel(f,text="LIFE BALANCE",
            font=ctk.CTkFont(family=FONT,size=9),text_color=DM
            ).grid(row=12,column=0,sticky="w",padx=16)
        self.score_l=ctk.CTkLabel(f,text="100",
            font=ctk.CTkFont(family=FONT,size=44,weight="bold"),text_color=CY)
        self.score_l.grid(row=13,column=0,sticky="w",padx=16,pady=(0,2))
        self.sev_l=ctk.CTkLabel(f,text="STATUS: NOMINAL",
            font=ctk.CTkFont(family=FONT,size=9,weight="bold"),text_color=CY)
        self.sev_l.grid(row=14,column=0,sticky="w",padx=16,pady=(0,10))

    # ── RIGHT: VITA AI Assistant ──
    def _build_right(self,p):
        f=ctk.CTkFrame(p,corner_radius=16,fg_color=PNL,border_width=1,border_color=BD)
        f.grid(row=0,column=2,sticky="nsew",padx=(4,0))
        f.grid_columnconfigure(0,weight=1); f.grid_rowconfigure(2,weight=1)

        # Header with avatar
        hdr=ctk.CTkFrame(f,fg_color="transparent")
        hdr.grid(row=0,column=0,sticky="ew",padx=12,pady=(10,0))
        hdr.grid_columnconfigure(1,weight=1)
        if self._avatar:
            ctk.CTkLabel(hdr,image=self._avatar,text="").grid(
                row=0,column=0,rowspan=2,padx=(0,6))
        else:
            ctk.CTkLabel(hdr,text="🌸",font=ctk.CTkFont(size=32)).grid(
                row=0,column=0,rowspan=2,padx=(0,6))
        ctk.CTkLabel(hdr,text="VITA AI",
            font=ctk.CTkFont(family=FONT,size=14,weight="bold"),
            text_color=PK).grid(row=0,column=1,sticky="sw")
        self._stl=ctk.CTkLabel(hdr,
            text="● Checking local model...",
            font=ctk.CTkFont(family=FONT,size=9),
            text_color=GD)
        self._stl.grid(row=1,column=1,sticky="nw")

        ctk.CTkFrame(f,height=1,fg_color=BD).grid(
            row=1,column=0,sticky="ew",padx=10,pady=(6,2))

        # Chat feed
        self._cf=ctk.CTkScrollableFrame(f,fg_color="#0B121D",corner_radius=10,
            border_width=1,border_color="#1a2744")
        self._cf.grid(row=2,column=0,sticky="nsew",padx=10,pady=(0,3))
        self._cf.grid_columnconfigure(0,weight=1)
        self._cr=0
        self._chat_busy=False
        self._chat_closed=False
        self._chat_events=queue.Queue()
        self._chat_response_text=""
        self._chat_poll_id=None
        self.after(250,self._refresh_local_ai_status)
        self._chat_scroll_pending=False
        self._chat_at_bottom=True
        self._cf._parent_canvas.bind("<Configure>",self._on_chat_canvas_configure,add="+")
        self._cf._parent_canvas.bind("<MouseWheel>",self._on_chat_scroll,add="+")
        self._cf._parent_canvas.bind("<Button-4>",self._on_chat_scroll,add="+")
        self._cf._parent_canvas.bind("<Button-5>",self._on_chat_scroll,add="+")
        self._cf._parent_canvas.bind("<B1-Motion>",self._on_chat_scroll,add="+")
        self._cf._parent_canvas.bind("<ButtonRelease-1>",self._on_chat_scroll,add="+")

        # Quick command chips
        ch=ctk.CTkFrame(f,fg_color="transparent",height=24)
        ch.grid(row=3,column=0,sticky="ew",padx=10,pady=(2,2))
        for lb,q in [("STATUS","overview"),("CPU","cpu"),("RAM","ram"),
                     ("🔋","battery"),("SCORE","score"),("🔒","security"),("🧹","cache")]:
            ctk.CTkButton(ch,text=lb,width=48,height=20,
                font=ctk.CTkFont(family=FONT,size=8,weight="bold"),
                fg_color=BTN,hover_color=BTH,text_color=PK,corner_radius=4,
                border_width=1,border_color=BD,
                command=lambda q=q:self._send(q)).pack(side="left",padx=1)

        # Input
        inp=ctk.CTkFrame(f,fg_color="transparent")
        inp.grid(row=4,column=0,sticky="ew",padx=10,pady=(2,10))
        inp.grid_columnconfigure(0,weight=1)
        self._ce=ctk.CTkEntry(inp,placeholder_text="Ask VITA AI...",
            font=ctk.CTkFont(family=FONT,size=10),fg_color="#0D1B2A",text_color=TX,
            border_color=BD,corner_radius=6,height=32)
        self._ce.grid(row=0,column=0,sticky="ew",padx=(0,4))
        self._ce.bind("<Return>",lambda e:self._send())
        ctk.CTkButton(inp,text="SEND",width=55,height=32,
            font=ctk.CTkFont(family=FONT,size=9,weight="bold"),
            fg_color=PK,hover_color="#E91E63",text_color="white",corner_radius=6,
            command=self._send).grid(row=0,column=1)

        # Welcome message
        self._bot_msg("Hello! VITA AI is ready to help with your system.\n"
                      "Ask about your system, security, or just chat! ♡")

    # ── Chat logic ──
    def _send(self, preset=None):
        if self._chat_busy: return
        q = preset or self._ce.get().strip()
        if not q: return
        submitted_at = datetime.now().isoformat(timespec="milliseconds")
        submitted_monotonic = time.perf_counter()
        if not preset: self._ce.delete(0,"end")
        self._user_msg(q)
        ql = q.lower()

        # Special commands handled locally
        if "security" in ql or ("scan" in ql and "cache" not in ql):
            self._start_security_scan(); return
        if any(k in ql for k in ["cache","clean","purge","temp"]):
            self._do_cache_clean(); return

        # Generative chat runs on the local Ollama service in a worker thread.
        with self._lock: snap=dict(self._snap) if self._snap else {}
        self._chat_busy=True
        self._ce.configure(state="disabled")
        self._chat_status=self._bot_msg("VITA AI is thinking…")
        self._chat_response_text=""
        diagnosis=self._diag
        logger.info("VITA message submitted at=%s", submitted_at)
        def generate():
            try:
                ready,reason=self.chat.check_model()
                if not ready:
                    self._chat_events.put(("unavailable",reason))
                    self._chat_events.put(("finish",None))
                    return
                self.chat.stream_response(q,snap,diagnosis,
                    on_chunk=lambda piece:self._chat_events.put(("chunk",piece)),
                    submitted_at=submitted_at,
                    submitted_monotonic=submitted_monotonic)
                self._chat_events.put(("finish",None))
            except Exception as exc:
                logger.exception("Local generative chat failed")
                self._chat_events.put(("error",str(exc)))
        threading.Thread(target=generate,name="vita-chat",daemon=True).start()
        self._chat_poll_id=self.after(40,self._drain_chat_events)

    def _drain_chat_events(self):
        if self._chat_closed or not self.winfo_exists(): return
        finished=False
        try:
            while True:
                event,value=self._chat_events.get_nowait()
                if event=="chunk":
                    self._chat_response_text+=value
                elif event=="unavailable":
                    if "not downloaded" in value.lower():
                        self._chat_response_text=(
                            "The local Qwen3 model is missing. Download it with "
                            "`ollama pull qwen3:0.6b`, then try again.")
                    elif "not running" in value.lower():
                        self._chat_response_text=(
                            "Ollama is offline or unreachable. Start Ollama and try again.\n\n"
                            f"Details: {value}")
                    else:
                        self._chat_response_text=(
                            "The local AI service is unavailable. Check that Ollama is "
                            "running and qwen3:0.6b is downloaded.\n\n"
                            f"Details: {value}")
                elif event=="error":
                    if self._chat_response_text:
                        self._chat_response_text+=f"\n\n[Generation interrupted: {value}]"
                    else:
                        self._chat_response_text=(
                            "Local AI generation failed. Check that Ollama is running "
                            "and qwen3:0.6b is downloaded. Details: " + value)
                    finished=True
                elif event=="finish":
                    finished=True
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            if self._chat_response_text:
                self._chat_status.configure(text=self._chat_response_text)
                self._scroll(force=False)
        except tk.TclError:
            return
        if finished:
            self._chat_busy=False
            try: self._ce.configure(state="normal")
            except tk.TclError: pass
            self._chat_poll_id=None
        else:
            self._chat_poll_id=self.after(40,self._drain_chat_events)

    def _refresh_local_ai_status(self):
        def check():
            ready,reason=self.chat.check_model()
            try:
                self.after(0,lambda:self._set_local_ai_status(ready,reason))
            except tk.TclError:
                pass
        threading.Thread(target=check,name="vita-model-check",daemon=True).start()

    def _set_local_ai_status(self, ready, _reason):
        if self._chat_closed or not self.winfo_exists(): return
        if ready:
            status="● Qwen3 0.6B · offline"
        elif "not downloaded" in _reason.lower():
            status="● Qwen3 model missing"
        elif "not running" in _reason.lower():
            status="● Ollama offline"
        else:
            status="● Local AI connection error"
        try:
            self._stl.configure(
                text=status,
                text_color=GR if ready else GD)
        except tk.TclError:
            pass

    def _user_msg(self, t):
        b=ctk.CTkFrame(self._cf,fg_color="#0D2844",corner_radius=6)
        b.grid(row=self._cr,column=0,sticky="e",padx=(40,4),pady=(2,1))
        ctk.CTkLabel(b,text=t,wraplength=300,justify="left",anchor="w",
            font=ctk.CTkFont(family=FONT,size=10),text_color=TX).pack(padx=8,pady=4)
        self._cr+=1; self._scroll()

    def _bot_msg(self, t):
        b=ctk.CTkFrame(self._cf,fg_color="#0F1A2E",corner_radius=6,
            border_width=1,border_color="#2A1545")
        b.grid(row=self._cr,column=0,sticky="w",padx=(4,40),pady=(1,2))
        ctk.CTkLabel(b,text="VITA AI",
            font=ctk.CTkFont(family=FONT,size=8,weight="bold"),
            text_color=PK).pack(anchor="w",padx=8,pady=(3,0))
        body=ctk.CTkLabel(b,text=t,wraplength=300,justify="left",anchor="w",
            font=ctk.CTkFont(family=FONT,size=10),text_color=TX)
        body.pack(padx=8,pady=(1,4))
        self._cr+=1; self._scroll(force=False)
        return body

    def _on_chat_canvas_configure(self, _event=None):
        if self._chat_at_bottom:
            self._schedule_chat_scroll()

    def _on_chat_scroll(self, _event=None):
        # Inspect after Tk applies the wheel or scrollbar movement.
        self.after_idle(self._update_chat_scroll_state)

    def _update_chat_scroll_state(self):
        try:
            _first,last=self._cf._parent_canvas.yview()
            self._chat_at_bottom=last >= 0.995
        except (tk.TclError, AttributeError):
            pass

    def _schedule_chat_scroll(self):
        if self._chat_scroll_pending or not self._chat_at_bottom: return
        self._chat_scroll_pending=True
        self.after_idle(self._run_chat_scroll)

    def _run_chat_scroll(self):
        self._chat_scroll_pending=False
        self._scroll(force=False)

    def _scroll(self, force=False):
        try:
            if force or self._chat_at_bottom:
                self._cf._parent_canvas.yview_moveto(1.0)
        except (tk.TclError, AttributeError): pass

    # ── ACTION BAR ──
    def _build_action_bar(self):
        bar=ctk.CTkFrame(self,corner_radius=0,fg_color=BG,height=58)
        bar.grid(row=2,column=0,sticky="ew")
        bar.grid_columnconfigure((0,1,2,3,4,5),weight=1)
        bf=ctk.CTkFont(family=FONT,size=9,weight="bold")

        ctk.CTkButton(bar,text="🔒 ANTIVIRUS SCAN",font=bf,
            fg_color=BTN,hover_color=BTH,text_color=RD,corner_radius=6,
            border_width=1,border_color=BD,
            command=self._start_security_scan).grid(row=0,column=0,sticky="ew",padx=(12,3),pady=8)
        ctk.CTkButton(bar,text="🧹 PURGE CACHE",font=bf,
            fg_color=BTN,hover_color=BTH,text_color=GD,corner_radius=6,
            border_width=1,border_color=BD,
            command=self._do_cache_clean).grid(row=0,column=1,sticky="ew",padx=3,pady=8)
        ctk.CTkButton(bar,text="❄ COOLING",font=bf,
            fg_color=BTN,hover_color=BTH,text_color=CY,corner_radius=6,
            border_width=1,border_color=BD,
            command=self._toggle_cooling).grid(row=0,column=3,sticky="ew",padx=3,pady=8)
        ctk.CTkButton(bar,text="📤 EXPORT",font=bf,
            fg_color=BTN,hover_color=BTH,text_color=GR,corner_radius=6,
            border_width=1,border_color=BD,
            command=self._export).grid(row=0,column=4,sticky="ew",padx=3,pady=8)
        ctk.CTkButton(bar,text="◈ API KEY",font=bf,
            fg_color=BTN,hover_color=BTH,text_color="#B388FF",corner_radius=6,
            border_width=1,border_color=BD,
            command=self._set_api_key).grid(row=0,column=5,sticky="ew",padx=(3,12),pady=8)

    def _build_taskbar(self):
        """Build a compact Windows-style taskbar for metrics and app actions."""
        self._taskbar = ctk.CTkFrame(
            self, fg_color="#121B27", corner_radius=16,
            border_width=1, border_color=BD, height=68)
        self._taskbar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._taskbar.grid_columnconfigure(0, weight=1)
        self._taskbar.grid_columnconfigure(1, weight=0)
        self._taskbar.grid_columnconfigure(2, weight=1)

        self._start_button = TaskbarButton(
            self._taskbar, text="⊞  Start", width=88, height=46,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            text_color=CY, corner_radius=12,
            command=lambda: self._show_start_menu(self._start_button),
            tooltip="Start menu and app shortcuts", base_color="#1A2938",
            hover_color="#274254")
        self._start_button.grid(row=0, column=0, sticky="w", padx=(10, 6), pady=9)

        metric_group = ctk.CTkFrame(self._taskbar, fg_color="transparent")
        metric_group.grid(row=0, column=1, pady=6)
        metric_specs = [
            ("cpu", "◉\nCPU", "Processor usage"),
            ("memory", "▤\nRAM", "Memory used and available"),
            ("battery", "◒\nBAT", "Battery charge and power state"),
            ("disk", "▣\nDISK", "System drive usage"),
            ("network", "⌁\nNET", "Network adapter status"),
        ]
        self._taskbar_metric_buttons = {}
        for index, (kind, label, tooltip) in enumerate(metric_specs):
            button = TaskbarButton(
                metric_group, text=label, width=58, height=48,
                font=ctk.CTkFont(family=FONT, size=9, weight="bold"),
                text_color=TX, corner_radius=10,
                command=lambda kind=kind: self._show_metric_panel(kind),
                tooltip=tooltip)
            button.grid(row=0, column=index, padx=2)
            self._taskbar_metric_buttons[kind] = button

        tray = ctk.CTkFrame(self._taskbar, fg_color="transparent")
        tray.grid(row=0, column=2, sticky="e", padx=(6, 10), pady=7)
        app_specs = [
            ("✦", "Open VITA AI", self._focus_chat),
            ("⛨", "Microsoft Defender quick scan", self._start_security_scan),
            ("❄", "Toggle low-impact cooling mode", self._toggle_cooling),
            ("⇧", "Export system report", self._export),
        ]
        for symbol, tooltip, command in app_specs:
            button = TaskbarButton(
                tray, text=symbol, width=38, height=40,
                font=ctk.CTkFont(family=FONT, size=15),
                text_color=TX, corner_radius=10,
                command=command, tooltip=tooltip)
            button.pack(side="left", padx=1)

        self._notification_button = TaskbarButton(
            tray, text="🔔", width=38, height=40,
            font=ctk.CTkFont(family="Segoe UI Emoji", size=15),
            text_color=TX, corner_radius=10,
            command=self._show_notification_center,
            tooltip="Notification center")
        self._notification_button.pack(side="left", padx=(6, 2))

        self._taskbar_clock_text = tk.StringVar(value="--:--\n--- --")
        self._clock_button = TaskbarButton(
            tray, textvariable=self._taskbar_clock_text, width=92, height=44,
            font=ctk.CTkFont(family=FONT, size=9, weight="bold"),
            text_color=TX, corner_radius=10,
            command=self._show_clock_panel, tooltip="Date, time, and session")
        self._clock_button.pack(side="left", padx=(3, 0))

    def _focus_chat(self):
        self._ce.focus_set()

    def _close_taskbar_panel(self):
        panel = getattr(self, "_taskbar_panel", None)
        if panel is not None:
            try:
                panel.destroy()
            except tk.TclError:
                pass
        self._taskbar_panel = None
        self._taskbar_panel_label = None
        self._taskbar_panel_kind = None

    def _open_taskbar_panel(self, anchor, title, subtitle="", width=330, height=220):
        self._close_taskbar_panel()
        panel = ctk.CTkToplevel(self)
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.configure(fg_color=PNL)
        panel.geometry(f"{width}x{height}")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(heading, text=title,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TX).grid(row=0, column=0, sticky="w")
        close_button = ctk.CTkButton(
            heading, text="×", width=28, height=26, corner_radius=8,
            fg_color=BTN, hover_color=BTH, text_color=TX,
            command=self._close_taskbar_panel)
        close_button.grid(row=0, column=1, sticky="e")
        if subtitle:
            ctk.CTkLabel(panel, text=subtitle,
                font=ctk.CTkFont(family=FONT, size=10),
                text_color=TX2, anchor="w").grid(
                    row=1, column=0, sticky="ew", padx=16, pady=(0, 5))

        body = ctk.CTkFrame(panel, fg_color="#0B121D", corner_radius=12)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 12))
        body.grid_columnconfigure(0, weight=1)

        panel.update_idletasks()
        x = anchor.winfo_rootx() + (anchor.winfo_width() - width) // 2
        y = anchor.winfo_rooty() - height - 10
        x = max(8, min(x, panel.winfo_screenwidth() - width - 8))
        y = max(8, min(y, panel.winfo_screenheight() - height - 8))
        panel.geometry(f"{width}x{height}+{x}+{y}")
        self._taskbar_panel = panel
        return panel, body

    def _snapshot_text(self, kind, snap):
        snap = snap or {}
        if kind == "cpu":
            value = snap.get("cpu_load")
            return (f"Current use   {value:.0f}%\n"
                    f"Logical cores   {os.cpu_count() or 'N/A'}\n"
                    "Source   System telemetry") if isinstance(value, (int, float)) else "Waiting for system telemetry…"
        if kind == "memory":
            used, total, available = (snap.get("ram_used_gb", -1),
                                      snap.get("ram_total_gb", -1),
                                      snap.get("ram_available_gb", -1))
            if total < 0:
                return "Memory details are not available yet."
            return (f"In use   {used:.1f} GB / {total:.1f} GB\n"
                    f"Available   {available:.1f} GB\n"
                    f"Memory load   {snap.get('ram_usage', 0):.0f}%")
        if kind == "battery":
            charge = snap.get("battery_charge_pct", -1)
            if charge < 0:
                return "Battery   Not available on this device\nPower state   Sensor unavailable"
            state = "Charging / plugged in" if snap.get("battery_plugged") else "On battery"
            return (f"Charge   {charge:.0f}%\nPower state   {state}\n"
                    f"Estimated health   {snap.get('battery_soh', -1):.0f}%")
        if kind == "disk":
            used, total, percent = (snap.get("disk_used_gb", -1),
                                    snap.get("disk_total_gb", -1),
                                    snap.get("disk_usage_percent", -1))
            if total < 0:
                return "System drive usage is not available."
            return (f"System drive   {used:.1f} GB used of {total:.1f} GB\n"
                    f"Used   {percent:.0f}%\nFree   {max(0, total - used):.1f} GB")
        if kind == "network":
            connected = snap.get("network_connected")
            if connected is None:
                return "Waiting for network adapter status…"
            status = "Connected" if connected else "No active network link"
            return (f"Adapter link   {status}\n"
                    "Status checks active non-loopback network interfaces.")
        if kind == "clock":
            return (f"{datetime.now().strftime('%A, %B %d, %Y')}\n"
                    f"Active session   {snap.get('session_mins', 0):.0f} minutes")
        if kind == "overview":
            if not snap:
                return "Waiting for system telemetry…"
            battery = snap.get("battery_charge_pct", -1)
            disk = snap.get("disk_usage_percent", -1)
            memory_available = snap.get("ram_available_gb", -1)
            battery_text = f"{battery:.0f}%" if battery >= 0 else "Unavailable"
            disk_text = f"{disk:.0f}% used" if disk >= 0 else "Unavailable"
            memory_text = (f"{snap.get('ram_usage', 0):.0f}% "
                           f"({memory_available:.1f} GB available)"
                           if memory_available >= 0 else "Unavailable")
            network_value = snap.get("network_connected")
            network_text = ("Waiting" if network_value is None else
                            "Connected" if network_value else "No active link")
            return (f"Processor   {snap.get('cpu_load', 0):.0f}%\n"
                    f"Memory   {memory_text}\n"
                    f"Battery   {battery_text}\n"
                    f"System drive   {disk_text}\n"
                    f"Network link   {network_text}")
        return "System status is not available yet."

    def _show_metric_panel(self, kind):
        button = self._taskbar_metric_buttons.get(kind)
        if not button:
            return
        titles = {
            "cpu": "Processor", "memory": "Memory", "battery": "Battery",
            "disk": "System drive", "network": "Network link",
        }
        panel, body = self._open_taskbar_panel(
            button, titles[kind], "Live System Vitals", width=340, height=230)
        label = ctk.CTkLabel(body, text=self._snapshot_text(kind, self._get_snap_safe()),
            font=ctk.CTkFont(family=FONT, size=12), text_color=TX,
            justify="left", anchor="w")
        label.grid(row=0, column=0, sticky="nw", padx=16, pady=16)
        self._taskbar_panel_label = label
        self._taskbar_panel_kind = kind

    def _show_start_menu(self, anchor):
        panel, body = self._open_taskbar_panel(
            anchor, "System Vitals", "Pinned tools and quick actions",
            width=390, height=450)
        shortcuts = [
            ("System overview", self._show_overview_panel),
            ("Memory", lambda: self._show_metric_panel("memory")),
            ("Battery", lambda: self._show_metric_panel("battery")),
            ("System drive", lambda: self._show_metric_panel("disk")),
            ("Network status", lambda: self._show_metric_panel("network")),
            ("Ask VITA AI", self._focus_chat),
            ("Microsoft Defender scan", self._start_security_scan),
            ("Cooling mode", self._toggle_cooling),
            ("Export report", self._export),
            ("Purge cache", self._do_cache_clean),
            ("OpenAI API key", self._set_api_key),
        ]
        for index, (label, command) in enumerate(shortcuts):
            row, column = divmod(index, 2)
            button = ctk.CTkButton(
                body, text=label, anchor="w", height=44, corner_radius=10,
                fg_color=BTN, hover_color=BTH, text_color=TX,
                font=ctk.CTkFont(family=FONT, size=10),
                command=lambda command=command: self._run_start_action(command))
            button.grid(row=row, column=column, sticky="ew", padx=6, pady=5)
        body.grid_columnconfigure((0, 1), weight=1)

    def _show_overview_panel(self):
        panel, body = self._open_taskbar_panel(
            self._start_button, "System overview", "Live System Vitals",
            width=350, height=260)
        self._taskbar_panel_label = ctk.CTkLabel(
            body, text=self._snapshot_text("overview", self._get_snap_safe()),
            font=ctk.CTkFont(family=FONT, size=11), text_color=TX,
            justify="left", anchor="w")
        self._taskbar_panel_label.grid(row=0, column=0, sticky="nw", padx=16, pady=16)
        self._taskbar_panel_kind = "overview"

    def _run_start_action(self, command):
        self._close_taskbar_panel()
        command()

    def _show_notification_center(self):
        panel, body = self._open_taskbar_panel(
            self._notification_button, "Notification center",
            "Live system status", width=340, height=260)
        self._taskbar_panel_label = ctk.CTkLabel(
            body, text=self._notification_text(self._get_snap_safe()),
            font=ctk.CTkFont(family=FONT, size=11), text_color=TX,
            justify="left", anchor="w")
        self._taskbar_panel_label.grid(row=0, column=0, sticky="nw", padx=16, pady=16)
        self._taskbar_panel_kind = "notifications"

    def _notification_text(self, snap):
        snap = snap or {}
        score = f"{self._diag.balance_score:.0f}/100" if self._diag else "Waiting for data"
        battery = snap.get("battery_charge_pct", -1)
        battery_text = f"{battery:.0f}%" if battery >= 0 else "Unavailable"
        network_value = snap.get("network_connected")
        network = ("Waiting for telemetry" if network_value is None else
                   "Connected" if network_value else "No active link")
        scan = self.security.get_status_summary()
        scan_state = scan.get("status", "ready").replace("_", " ").title()
        return (f"Life balance   {score}\n"
                f"Battery   {battery_text}\n"
                f"Network   {network}\n"
                f"Defender   {scan_state}\n"
                f"Focus session   {snap.get('session_mins', 0):.0f} min")

    def _show_clock_panel(self):
        panel, body = self._open_taskbar_panel(
            self._clock_button, "Date and time", "Local device time",
            width=300, height=180)
        self._taskbar_panel_label = ctk.CTkLabel(
            body, text=self._snapshot_text("clock", self._get_snap_safe()),
            font=ctk.CTkFont(family=FONT, size=12), text_color=TX,
            justify="left", anchor="w")
        self._taskbar_panel_label.grid(row=0, column=0, sticky="nw", padx=16, pady=16)
        self._taskbar_panel_kind = "clock"

    def _update_taskbar(self, snap):
        if not hasattr(self, "_taskbar_metric_buttons"):
            return
        snap = snap or {}
        cpu = snap.get("cpu_load")
        ram = snap.get("ram_usage")
        battery = snap.get("battery_charge_pct", -1)
        disk = snap.get("disk_usage_percent", -1)
        network = snap.get("network_connected")
        values = {
            "cpu": f"◉\n{cpu:.0f}%" if isinstance(cpu, (int, float)) else "◉\nCPU",
            "memory": f"▤\n{ram:.0f}%" if isinstance(ram, (int, float)) else "▤\nRAM",
            "battery": f"◒\n{battery:.0f}%" if battery >= 0 else "◒\nN/A",
            "disk": f"▣\n{disk:.0f}%" if disk >= 0 else "▣\nN/A",
            "network": ("⌁\n…" if network is None else
                        "⌁\nON" if network else "⌁\nOFF"),
        }
        for kind, value in values.items():
            self._taskbar_metric_buttons[kind].configure(text=value)
        if getattr(self, "_taskbar_panel_label", None) is not None:
            kind = self._taskbar_panel_kind
            text = (self._notification_text(snap) if kind == "notifications"
                    else self._snapshot_text(kind, snap))
            self._taskbar_panel_label.configure(text=text)

    # ── FOOTER ──
    def _build_footer(self):
        ft=ctk.CTkFrame(self,corner_radius=0,fg_color="#0B121D",height=36)
        ft.grid(row=3,column=0,sticky="ew"); ft.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(ft,
            text="◈ TEAM VITALS — Leader: Akash Soni | Ansh Jangid · Abhinav Pratap Singh · "
                 "Ansh Porwal · Anmol Tanwar | Supervisor: Dr. Vishal Srivastava",
            font=ctk.CTkFont(family=FONT,size=9),text_color=DM).grid(row=0,column=0,pady=7)

    # ==================================================================
    # FEATURE ACTIONS
    # ==================================================================
    def _start_security_scan(self):
        """Run Defender away from Tk's event loop so the dashboard stays responsive."""
        if getattr(self, "_scan_running", False):
            self._bot_msg("A Defender scan is already running.")
            return
        self._scan_running = True
        self._bot_msg("Starting Microsoft Defender quick scan. This can take several minutes.")
        threading.Thread(target=self._run_security_scan, daemon=True).start()

    def _run_security_scan(self):
        try:
            result = self.security.run_quick_scan()
        except Exception as exc:
            result = {"status": "error", "message": str(exc)}
        self.after(0, lambda result=result: self._finish_security_scan(result))

    def _finish_security_scan(self, result):
        self._scan_running = False
        if result.get("status") == "completed":
            self._bot_msg(
                f"Microsoft Defender quick scan completed in "
                f"{result['duration_sec']:.1f} seconds.\n\n{result['message']}"
            )
        else:
            self._bot_msg(f"Defender scan failed: {result.get('message', 'Unknown error')}")
        self._upd_security()

    def _do_security_scan(self):
        return self._start_security_scan()

    def _do_cache_clean(self):
        self._bot_msg("🧹 Scanning temp files... ✦")
        self.update_idletasks()
        try:
            scan = self.optimizer.cleaner.scan_temp_files()
            self._bot_msg(f"Found {scan['temp_files_found']} temp files "
                          f"({scan['total_size_mb']:.1f} MB)\nPurging now... 🌸")
            self.update_idletasks()
            result = self.optimizer.cleaner.purge_temp_files()
            if hasattr(self.db, "insert_cache_clean"):
                self.db.insert_cache_clean(
                    result["files_deleted"], result["bytes_freed"],
                    result["mb_freed"], result["duration_sec"])
            self._bot_msg(
                f"🧹 Cache Purge Complete!\n\n"
                f"▸ Files deleted: {result['files_deleted']}\n"
                f"▸ Space freed: {result['mb_freed']:.1f} MB\n"
                f"▸ Duration: {result['duration_sec']:.1f}s\n"
                f"▸ Lifetime cleaned: {result['total_lifetime_cleaned_mb']:.1f} MB ✦")
        except Exception as e:
            self._bot_msg(f"Clean error: {e}")

    def _toggle_cooling(self):
        try:
            self._toggle_cool()
        except Exception as exc:
            self._bot_msg(f"Cooling mode could not be changed: {exc}")

    def _toggle_cool_legacy(self):
        if self.optimizer.cooling.is_active:
            r = self.optimizer.cooling.deactivate()
            self._bot_msg(f"❄ Cooling off. {r.get('processes_restored',0)} processes restored ✦")
        else:
            r = self.optimizer.cooling.activate()
            self._bot_msg(f"❄ Cooling active! {r.get('processes_throttled',0)} hot processes throttled 🌸")

    def _toggle_cool(self):
        if self.optimizer.cooling.is_active:
            self.optimizer.cooling.deactivate()
            self._bot_msg("Cooling mode disabled. VITA AI process priority restored.")
        else:
            self.optimizer.cooling.activate()
            self._bot_msg("Cooling mode enabled. VITA AI process priority lowered to reduce its CPU impact.")

    def _set_api_key(self):
        if not hasattr(self.chat, "set_api_key"):
            self._bot_msg("This checkout includes offline chat only; OpenAI API setup is unavailable.")
            return
        key = simpledialog.askstring("◈ API Key Setup",
            "Enter your OpenAI API key to unlock ChatGPT:\n\n"
            "• Get one at: platform.openai.com/api-keys\n"
            "• Key must start with 'sk-'\n"
            "• Free tier works fine!",
            parent=self)
        if key and key.strip():
            key = key.strip()
            if not key.startswith("sk-"):
                messagebox.showwarning("Invalid Key",
                    "OpenAI API keys start with 'sk-'.\n\n"
                    "The key you entered doesn't look right.\n"
                    "Get your key from platform.openai.com/api-keys")
                return
            self.chat.set_api_key(key)
            if self.chat.is_online:
                self._bot_msg("🟢 ChatGPT connected successfully! 🌸♡\n"
                              "I can now chat about anything!")
                self._stl.configure(text="● Online (ChatGPT)",text_color=GR)
            else:
                self._bot_msg("🔴 Connection failed. Check your key and try again.\n"
                              "Make sure: pip install openai")

    def _export(self):
        try:
            ed = self.db.fetch_full_analytics_export()
            ed["export_time"] = datetime.now().isoformat(timespec="seconds")
            ed["app"] = "SisVi+ Ultimate v1.0"
            if self._diag:
                ed["diagnosis"] = {
                    "score": self._diag.balance_score,
                    "severity": self._diag.severity}
            with self._lock: snap = dict(self._snap) if self._snap else {}
            ed["security"] = self.security.get_status_summary()
            ed["optimizer"] = self.optimizer.get_status()
            fn = f"sisvi_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            fp = filedialog.asksaveasfilename(
                title="Export Report", initialfile=fn,
                defaultextension=".json", filetypes=[("JSON","*.json")])
            if not fp: return
            with open(fp,"w",encoding="utf-8") as f:
                json.dump(ed, f, indent=2, default=str)
            self._bot_msg(f"📤 Report exported! 🌸\n{fp}")
        except Exception as e:
            messagebox.showerror("Export", str(e))

    # ==================================================================
    # UI REFRESH TICK
    # ==================================================================
    def _tick(self):
        try:
            with self._lock: snap = dict(self._snap) if self._snap else None
            if snap:
                self._update_taskbar(snap)
                self._chk_brk(snap["session_mins"])
                diag = self.ai.analyze(
                    cpu_load=snap["cpu_load"],
                    ram_usage=snap["ram_usage"],
                    storage_health=snap["storage_health"],
                    battery_soh=snap["battery_soh"],
                    battery_charge_pct=snap.get("battery_charge_pct"),
                    battery_plugged=snap.get("battery_plugged",False),
                    session_mins=snap["session_mins"],
                    breaks_ignored_count=self._brk_ign)
                self._diag = diag
                self._upd_left(snap)
                self._upd_center(snap, diag)
                self._upd_security()

                now = time.time()
                if now - self._db_last >= 15.0:
                    self.db.insert_telemetry_log(
                        cpu_load=snap["cpu_load"],
                        ram_usage=snap["ram_usage"],
                        storage_health=snap["storage_health"],
                        battery_soh=snap["battery_soh"],
                        battery_charge=snap.get("battery_charge_pct"),
                        battery_plugged=snap.get("battery_plugged",False),
                        session_mins=snap["session_mins"],
                        balance_score=diag.balance_score,
                        severity=diag.severity)
                    self._db_last = now
        except Exception as e:
            logger.error(f"Tick: {e}")
        finally:
            self.after(self._ui_ms, self._tick)

    def _mc(self, v, warn, crit):
        """Metric color based on thresholds."""
        if v >= crit: return RD
        if v >= warn: return GD
        return CY

    def _upd_left(self, s):
        """Update left panel metrics."""
        cpu=s["cpu_load"]; ram=s["ram_usage"]
        sto=s.get("disk_usage_percent", -1); bsoh=s["battery_soh"]
        bc=s.get("battery_charge_pct",-1); plug=s.get("battery_plugged",False)

        self.cpu_v.configure(text=f"{cpu:.0f}%")
        self.cpu_b.set(min(1,cpu/100))
        self.cpu_b.configure(progress_color=self._mc(cpu,80,92))

        self.ram_v.configure(text=f"{ram:.0f}%")
        self.ram_b.set(min(1,ram/100))
        self.ram_b.configure(progress_color=self._mc(ram,85,95))

        self.sto_v.configure(text=f"{sto:.0f}%" if sto >= 0 else "N/A")
        self.sto_b.set(min(1,sto/100) if sto >= 0 else 0)
        self.sto_b.configure(progress_color=self._mc(sto,80,95))

        if bsoh is None or bsoh < 0:
            self.bat_v.configure(text="N/A"); self.bat_b.set(0)
            self.bat_c.configure(text="▸ Desktop (no battery)")
        else:
            self.bat_v.configure(text=f"{bsoh:.0f}%")
            self.bat_b.set(min(1,bsoh/100))
            self.bat_b.configure(progress_color=self._mc(100-bsoh,20,35))
            ct = f"{bc:.0f}%" if bc and bc >= 0 else "N/A"
            self.bat_c.configure(
                text=f"▸ {ct} {'⚡Plugged' if plug else '🔋Battery'}")

    def _upd_center(self, s, d):
        """Update center panel wellbeing."""
        sm = s["session_mins"]
        ts = int(sm * 60); h, r = divmod(ts, 3600); m, sec = divmod(r, 60)
        self.sess_l.configure(
            text=f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}")

        rem = BRKM - (sm % BRKM)
        if rem == BRKM and sm > 0: rem = 0
        rm, rs = int(rem), int((rem - int(rem)) * 60)
        self.brk_l.configure(text=f"{rm:02d}:{rs:02d}")
        self.brk_pb.set(min(1, (sm % BRKM) / BRKM if BRKM > 0 else 0))

        if sm < 45:
            self.focus_b.configure(text="● FOCUSED",fg_color="#0D3320",text_color=GR)
        elif sm < 90:
            self.focus_b.configure(text="● STRETCH",fg_color="#3E2723",text_color=GD)
        else:
            self.focus_b.configure(text="● OVERDUE",fg_color="#3B0A0A",text_color=RD)

        self.ign_l.configure(text=f"Overridden: {self._brk_ign}")
        c = self.ai.severity_to_color(d.severity)
        self.score_l.configure(text=f"{d.balance_score:.0f}", text_color=c)
        st = {"good":"NOMINAL","moderate":"ELEVATED","warning":"WARNING","critical":"CRITICAL"}
        self.sev_l.configure(text=f"STATUS: {st.get(d.severity,'?')}", text_color=c)

    def _upd_security(self):
        """Update security status in left panel."""
        try:
            ss = self.security.get_status_summary()
            if ss.get("status") == "completed":
                self.sec_st.configure(text="LAST SCAN COMPLETE",fg_color="#12372D",text_color=GR)
                self.sec_info.configure(text="Review Windows Security for scan findings")
                return
            if not ss.get("available", False):
                self.sec_st.configure(text="SCAN UNAVAILABLE",fg_color=BTN,text_color=GD)
                self.sec_info.configure(text=ss.get("message", "Microsoft Defender was not found"))
                return
            self.sec_st.configure(text="DEFENDER READY",fg_color=BTN,text_color=CY)
            self.sec_info.configure(text="Microsoft Defender quick scan is available")
            return
            if ss["clean"]:
                self.sec_st.configure(text="● PROTECTED",fg_color="#0D3320",text_color=GR)
                self.sec_info.configure(
                    text=f"Shield active • {ss['processes_scanned']} processes • 0 threats")
            else:
                self.sec_st.configure(text="● THREATS",fg_color="#3B0A0A",text_color=RD)
                self.sec_info.configure(text=f"{len(ss['threats'])} threats detected!")
        except: pass

    # ==================================================================
    # BREAK LOGIC
    # ==================================================================
    def _chk_brk(self, sm):
        ic = int(sm // BRKM); lc = int(self._brk_last // BRKM)
        if ic > lc and ic > 0:
            self._brk_last = sm; self._pbrk()

    def _pbrk(self):
        tb = messagebox.askyesno("🌸 Break Time!",
            "VITA AI says: take a break!\n"
            "Your body needs rest ♡\n\nTake a break?")
        if tb: self._manual_break()
        else: self._brk_ign += 1

    def _manual_break(self):
        cm = self.telem.get_unbroken_session_minutes()
        if self._sess_id:
            self.db.end_session_log(self._sess_id, duration_mins=cm, break_taken=True)
        self.telem.reset_session_timer()
        self._brk_last = 0; self._brk_ign = 0
        self._sess_id = self.db.start_session_log("focus")

    # ==================================================================
    # SHUTDOWN
    # ==================================================================
    def _on_close(self):
        self._chat_closed=True
        try:
            if self._sess_id:
                self.db.end_session_log(
                    self._sess_id,
                    duration_mins=self.telem.get_unbroken_session_minutes(),
                    break_taken=False)
            self.telem.stop(timeout=3.0)
            self.db.close()
        except Exception as e:
            logger.error(f"Shutdown: {e}")
        finally:
            self.destroy()


def main():
    app = SystemVitalsDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
