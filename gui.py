from selection_window import show_video_selection_window
import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import json
import re
import shutil
from pathvalidate import sanitize_filename
import os


class UdemyDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Udemy Course Downloader - Eng. Mohamed Gomaa")
        self.config_path = "config.json"
        self.ffmpeg_processes = []
        self.create_widgets()
        self.ffmpeg_path = "ffmpeg"  # Assume ffmpeg is in PATH
        self.load_config()

    def setup_password_field(self, entry_widget):
        """Configure an entry widget to show asterisks by default and reveal on hover."""
        entry_widget.config(show="*")
        
        def on_enter(event):
            entry_widget.config(show="")
            
        def on_leave(event):
            entry_widget.config(show="*")
            
        entry_widget.bind("<Enter>", on_enter)
        entry_widget.bind("<Leave>", on_leave)

    def create_widgets(self):
        # Modern glass-like style
        # Brown Material Skin Colors
        bg_main = "#4E342E"  # brown dark
        bg_frame = "#6D4C41"  # brown medium
        bg_entry = "#A1887F"  # brown light
        fg_text = "#FFF8E1"  # cream
        fg_label = "#FFCCBC"  # light orange
        accent = "#D84315"    # deep orange accent
        accent2 = "#8D6E63"   # muted brown

        self.root.configure(bg=bg_main)
        self.root.grid_rowconfigure(100, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        label_style = {"bg": bg_main, "fg": fg_label, "font": ("Segoe UI", 11, "bold")}
        entry_style = {"bg": bg_entry, "fg": bg_main, "insertbackground": fg_text, "highlightbackground": accent2, "font": ("Segoe UI", 11)}
        button_style = {"bg": accent2, "fg": fg_label, "activebackground": accent, "activeforeground": fg_text, "font": ("Segoe UI", 11, "bold")}
        check_style = {"bg": bg_main, "fg": fg_label, "activebackground": bg_main, "activeforeground": fg_label, "selectcolor": bg_entry, "font": ("Segoe UI", 11)}

        # Add extra top padding to window and title
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1024, 768
        base_w = max(820, min(1000, sw - 120))
        base_h = max(620, min(800, sh - 160))
        self.root.geometry(f"{base_w}x{base_h}+80+50")  # Adaptive default size
        self.root.minsize(720, 520)
        self.root.resizable(True, True)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
        for i in range(8):
            self.root.grid_rowconfigure(i, weight=0)
        self.root.grid_rowconfigure(100, weight=1)
        title = tk.Label(self.root, text="Udemy Course Downloader", font=("Segoe UI", 20, "bold"), bg=bg_main, fg=accent)
        title.grid(row=0, column=0, columnspan=4, pady=(40, 20), padx=40, sticky="nsew")

        # Add a canvas and scrollbar for main content
        canvas_frame = tk.Frame(self.root, bg=bg_main)
        canvas_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(canvas_frame, bg=bg_frame, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_y = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x = tk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        # Make the canvas expandable
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # Frame inside canvas
        main_frame = tk.Frame(canvas, bg=bg_frame)
        main_frame_id = canvas.create_window((0,0), window=main_frame, anchor="nw")
        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        main_frame.bind("<Configure>", on_configure)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        for i in range(4):
            main_frame.grid_columnconfigure(i, weight=1)
        for i in range(12):
            main_frame.grid_rowconfigure(i, weight=0)

        row = 0
        def add_tooltip(widget, text):
            def on_enter(e):
                widget.tooltip = tk.Toplevel(widget)
                widget.tooltip.wm_overrideredirect(True)
                x = widget.winfo_rootx() + 20
                y = widget.winfo_rooty() + 20
                widget.tooltip.wm_geometry(f"+{x}+{y}")
                label = tk.Label(widget.tooltip, text=text, bg=bg_frame, fg=accent, font=("Segoe UI", 9), relief="solid", borderwidth=1)
                label.pack()
            def on_leave(e):
                if hasattr(widget, 'tooltip'):
                    widget.tooltip.destroy()
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        # Course URL
        lbl_course = tk.Label(main_frame, text="Course URL:", **label_style)
        lbl_course.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.course_url_entry = tk.Entry(main_frame, width=60, **entry_style)
        self.course_url_entry.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        
        def clean_course_url(event):
            url = self.course_url_entry.get().strip()
            if "/learn/lecture/" in url:
                clean_url = url.split("/learn/lecture/")[0]
                self.course_url_entry.delete(0, tk.END)
                self.course_url_entry.insert(0, clean_url)
                
        self.course_url_entry.bind("<FocusOut>", clean_course_url)
        add_tooltip(lbl_course, "Paste the Udemy course URL here.")
        row += 1

        # Access Token
        lbl_token = tk.Label(main_frame, text="Access Token:", **label_style)
        lbl_token.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.token_entry = tk.Entry(main_frame, width=60, **entry_style)
        self.token_entry.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        self.setup_password_field(self.token_entry)
        add_tooltip(lbl_token, "Paste your Udemy access token here.")
        row += 1

        # Udemy Type Selection
        lbl_udemy_type = tk.Label(main_frame, text="Udemy Type:", **label_style)
        lbl_udemy_type.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.udemy_type_var = tk.StringVar(value="normal")
        udemy_type_frame = tk.Frame(main_frame, bg=bg_frame)
        udemy_type_frame.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        tk.Radiobutton(udemy_type_frame, text="Normal Udemy (www.udemy.com)", variable=self.udemy_type_var, value="normal", **check_style).pack(side="left", padx=(0, 20))
        tk.Radiobutton(udemy_type_frame, text="Udemy Business (enterprise)", variable=self.udemy_type_var, value="business", **check_style).pack(side="left")
        add_tooltip(lbl_udemy_type, "Choose between normal Udemy or Udemy Business/Enterprise portal.")
        row += 1

        # Chapter
        lbl_chapter = tk.Label(main_frame, text="Chapter (e.g. 1,3-5):", **label_style)
      
        self.chapter_entry = tk.Entry(main_frame, width=20, **entry_style)
 
        add_tooltip(lbl_chapter, "Specify chapters to download.")
        row += 1

        # Lecture/Video Number
        lbl_lecture = tk.Label(main_frame, text="Video (e.g. 1,3-5):", **label_style)
       
        self.lecture_entry = tk.Entry(main_frame, width=20, **entry_style)
   
        add_tooltip(lbl_lecture, "Specify specific lectures/videos to download within the selected chapters.")
        row += 1

        # Quality
        lbl_quality = tk.Label(main_frame, text="Quality:", **label_style)
        lbl_quality.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        from tkinter import ttk
        self.quality_entry = ttk.Combobox(main_frame, values=["2160", "1440", "1080", "720", "480", "360"], width=8)
        self.quality_entry.set("720")
        self.quality_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_quality, "Video quality (e.g. 720, 1080)")
        row += 1

        # Language Selection - ENHANCED
        lbl_lang = tk.Label(main_frame, text="Caption Languages:", **label_style)
        lbl_lang.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        
        # Create a frame for language options
        lang_frame = tk.Frame(main_frame, bg=bg_frame)
        lang_frame.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        
        self.lang_var = tk.StringVar(value="en,ar")
        
        # Language options
        lang_options = [
            ("None", ""),
            ("English only", "en"),
            ("Arabic only", "ar"),
            ("English + Arabic", "en,ar"),
            ("All available", "all")
        ]
        
        for i, (display_text, value) in enumerate(lang_options):
            rb = tk.Radiobutton(
                lang_frame, 
                text=display_text, 
                variable=self.lang_var, 
                value=value,
                **check_style
            )
            rb.pack(side="left", padx=(0, 15))
        
        add_tooltip(lbl_lang, "Select which caption languages to download. English+Arabic is recommended for bilingual support.")
        row += 1

        # Connection Speed (replaces Concurrent Downloads)
        lbl_concurrent = tk.Label(main_frame, text="Connection Speed:", **label_style)
        lbl_concurrent.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        
        self.connection_speed = tk.StringVar(value="medium")  # Default to medium
        
        speed_frame = tk.Frame(main_frame, bg=bg_frame)
        speed_frame.grid(row=row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        
        tk.Radiobutton(speed_frame, text="Slow (1-5)", variable=self.connection_speed, value="slow", **check_style).pack(side="left", padx=(0, 20))
        tk.Radiobutton(speed_frame, text="Medium (10)", variable=self.connection_speed, value="medium", **check_style).pack(side="left", padx=(0, 20))
        tk.Radiobutton(speed_frame, text="Fast (20-30)", variable=self.connection_speed, value="fast", **check_style).pack(side="left")
        
        add_tooltip(lbl_concurrent, "Select your internet connection speed\n• Slow: 1-5 concurrent downloads\n• Medium: 10 concurrent downloads (recommended)\n• Fast: 20-30 concurrent downloads")
        
        row += 1

        # Output Directory
        lbl_out = tk.Label(main_frame, text="Output Directory:", **label_style)
        lbl_out.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        self.out_entry = tk.Entry(main_frame, width=40, **entry_style)
        self.out_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        btn_browse = tk.Button(main_frame, text="Browse", command=self.browse_out, **button_style)
        btn_browse.grid(row=row, column=2, sticky="nsew", pady=4, padx=4)
        add_tooltip(lbl_out, "Choose where downloads will be saved.")
        row += 1

        # HIDDEN: Log Level - kept for compatibility but not shown in UI
        self.loglevel_entry = tk.Entry(main_frame, width=10, **entry_style)
        # lbl_loglevel = tk.Label(main_frame, text="Log Level:", **label_style)
        # lbl_loglevel.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        # self.loglevel_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        # add_tooltip(lbl_loglevel, "Set log verbosity (e.g. info, debug)")
        # row += 1


        # HIDDEN: Browser (for cookies) - kept for compatibility but not shown in UI
        self.browser_entry = tk.Entry(main_frame, width=15, **entry_style)
        # lbl_browser = tk.Label(main_frame, text="Browser (for cookies):", **label_style)
        # lbl_browser.grid(row=row, column=0, sticky="e", pady=4, padx=4)
        # self.browser_entry.grid(row=row, column=1, sticky="nsew", pady=4, padx=4)
        # add_tooltip(lbl_browser, "Browser used for cookies export.")
        # row += 1

        # Separator
        sep1 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep1.grid(row=2, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Flags Frame
        flags_frame = tk.LabelFrame(self.root, text="Options", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        flags_frame.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(4):
            flags_frame.grid_columnconfigure(i, weight=1)
        for i in range(4):
            flags_frame.grid_rowconfigure(i, weight=0)


        # HIDDEN: Use H265 - Default ON, kept for compatibility but not shown
        self.use_h265 = tk.BooleanVar(value=True)
        
        # HIDDEN: Use NVENC - Default ON, kept for compatibility but not shown
        self.use_nvenc = tk.BooleanVar(value=True)
        
        # Download Captions - Default ON
        self.download_captions = tk.BooleanVar(value=True)
        
        # Download Assets - Default ON
        self.download_assets = tk.BooleanVar(value=True)
        
        # Download Quizzes - Default ON
        self.download_quizzes = tk.BooleanVar(value=True)
        
        # HIDDEN: Keep VTT - kept for compatibility but not shown
        self.keep_vtt = tk.BooleanVar()
        
        self.skip_lectures = tk.BooleanVar()
        self.skip_hls = tk.BooleanVar()
        
        # HIDDEN: Info Only - kept for compatibility but not shown
        self.info = tk.BooleanVar()
        
        # HIDDEN: ID as Course Name - kept for compatibility but not shown
        self.id_as_course_name = tk.BooleanVar()
        
        self.subscription_course = tk.BooleanVar()
        self.save_to_file = tk.BooleanVar()
        self.load_from_file = tk.BooleanVar()
        
        # HIDDEN: Continue Lecture Numbers - kept for compatibility but not shown
        self.continue_lecture_numbers = tk.BooleanVar()

        flag_row = 0
        tk.Checkbutton(flags_frame, text="Download Captions", variable=self.download_captions, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Download Assets", variable=self.download_assets, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Download Quizzes", variable=self.download_quizzes, **check_style).grid(row=flag_row, column=2, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Skip Lectures", variable=self.skip_lectures, **check_style).grid(row=flag_row, column=3, sticky="w", padx=4, pady=2)
        flag_row += 1
        tk.Checkbutton(flags_frame, text="Skip HLS (check if segmentation issue)", variable=self.skip_hls, **check_style).grid(row=flag_row, column=0, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Udemy Personal Plan", variable=self.subscription_course, **check_style).grid(row=flag_row, column=1, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Save to File", variable=self.save_to_file, **check_style).grid(row=flag_row, column=2, sticky="w", padx=4, pady=2)
        tk.Checkbutton(flags_frame, text="Load from File", variable=self.load_from_file, **check_style).grid(row=flag_row, column=3, sticky="w", padx=4, pady=2)

        # Separator
        sep2 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep2.grid(row=4, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Advanced Frame
        adv_frame = tk.LabelFrame(self.root, text="Advanced", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        adv_frame.grid(row=5, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(4):
            adv_frame.grid_columnconfigure(i, weight=1)
        for i in range(2):
            adv_frame.grid_rowconfigure(i, weight=0)

        adv_row = 0
        # HIDDEN: H265 CRF - kept for compatibility but not shown
        self.h265_crf_entry = tk.Entry(adv_frame, width=10, **entry_style)
        # tk.Label(adv_frame, text="H265 CRF:", **label_style).grid(row=adv_row, column=0, sticky="e", pady=4, padx=4)
        # self.h265_crf_entry.grid(row=adv_row, column=1, sticky="nsew", pady=4, padx=4)
        
        # HIDDEN: H265 Preset - kept for compatibility but not shown
        self.h265_preset_entry = tk.Entry(adv_frame, width=10, **entry_style)
        # tk.Label(adv_frame, text="H265 Preset:", **label_style).grid(row=adv_row, column=2, sticky="e", pady=4, padx=4)
        # self.h265_preset_entry.grid(row=adv_row, column=3, sticky="nsew", pady=4, padx=4)
        # adv_row += 1

        tk.Label(adv_frame, text="Decryption Key:", **label_style).grid(row=adv_row, column=0, sticky="e", pady=4, padx=4)
        self.decryption_key_entry = tk.Entry(adv_frame, width=60, **entry_style)
        self.decryption_key_entry.grid(row=adv_row, column=1, columnspan=3, sticky="nsew", pady=4, padx=4)
        self.setup_password_field(self.decryption_key_entry)
        
        def clean_decryption_key(event):
            key_text = self.decryption_key_entry.get().strip()
            if ":" in key_text:
                # Handle format KID:KEY - keep only KEY (second part)
                parts = key_text.split(":")
                if len(parts) >= 2:
                    clean_key = parts[1].strip()
                    self.decryption_key_entry.delete(0, tk.END)
                    self.decryption_key_entry.insert(0, clean_key)
                    
        self.decryption_key_entry.bind("<FocusOut>", clean_decryption_key)

        # Separator
        sep3 = tk.Frame(self.root, height=2, bd=0, bg=accent2)
        sep3.grid(row=6, column=0, columnspan=4, sticky="ew", padx=40, pady=(10, 10))

        # Buttons Frame
        btn_frame = tk.Frame(self.root, bg=bg_main)
        btn_frame.grid(row=7, column=0, columnspan=4, sticky="nsew", padx=40, pady=(0,10))
        for i in range(4):
            btn_frame.grid_columnconfigure(i, weight=1)
        btn_frame.grid_rowconfigure(0, weight=1)

        btn_start = tk.Button(btn_frame, text="Start", command=self.start_full_process, bg=accent, fg=fg_text, font=("Segoe UI", 12, "bold"), relief="flat")
        btn_start.grid(row=0, column=0, pady=10, padx=10, sticky="nsew")
        add_tooltip(btn_start, "Download course, decrypt DRM, combine video/audio, and cleanup")
        
        btn_decrypt = tk.Button(btn_frame, text="Decrypt Only", command=self.start_decrypt_combine_only, bg="#7B1FA2", fg=fg_text, font=("Segoe UI", 11, "bold"), relief="flat")
        btn_decrypt.grid(row=0, column=1, pady=10, padx=10, sticky="nsew")
        add_tooltip(btn_decrypt, "Process already downloaded files: decrypt, combine audio/video, and rename")
        
        btn_verify = tk.Button(btn_frame, text="Verify Downloads", command=self.verify_downloads, bg="#009688", fg=fg_text, font=("Segoe UI", 11, "bold"), relief="flat")
        btn_verify.grid(row=0, column=2, pady=10, padx=10, sticky="nsew")
        add_tooltip(btn_verify, "Verify downloaded files against manifest and generate report")
        
        btn_save = tk.Button(btn_frame, text="Save Config", command=self.save_config, bg=accent2, fg=fg_label, font=("Segoe UI", 12, "bold"), relief="flat")
        btn_save.grid(row=0, column=3, pady=10, padx=10, sticky="nsew")
        add_tooltip(btn_save, "Save current settings to config.json")
        
        btn_stop = tk.Button(btn_frame, text="Stop & Clean", command=self.stop_and_clean, bg="#B71C1C", fg=fg_text, font=("Segoe UI", 12, "bold"), relief="flat")
        btn_stop.grid(row=0, column=4, pady=10, padx=10, sticky="nsew")
        add_tooltip(btn_stop, "Stop all processes and clean temporary files")

        # Status Frame
        status_frame = tk.LabelFrame(self.root, text="Status Log", bg=bg_frame, fg=accent, font=("Segoe UI", 12, "bold"), bd=2, relief="groove")
        status_frame.grid(row=100, column=0, columnspan=4, sticky="nsew", padx=40, pady=20)
        status_frame.grid_rowconfigure(0, weight=1)
        status_frame.grid_columnconfigure(0, weight=1)
        self.main_status_text = tk.Text(status_frame, height=10, width=80, state="disabled", bg=bg_entry, fg=bg_main, font=("Consolas", 11), relief="flat")
        self.main_status_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        # Backward-compat: keep old name pointing to main log until progress window appears
        self.status_text = self.main_status_text

    def stop_and_clean(self):
        # Signal stop if running
        if hasattr(self, 'stop_event') and self.stop_event:
            self.stop_event.set()
        # Terminate all running ffmpeg processes
        for proc in getattr(self, 'ffmpeg_processes', []):
            try:
                if proc.poll() is None:
                    proc.terminate()
                    self.log("Terminated ffmpeg process.")
            except Exception as e:
                self.log(f"Error terminating ffmpeg: {e}")
        self.ffmpeg_processes = []
        # Remove all files in ./logs/* and ./temp/*
        for folder in ["logs", "temp"]:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path):
                for f in os.listdir(folder_path):
                    try:
                        fp = os.path.join(folder_path, f)
                        if os.path.isfile(fp):
                            os.remove(fp)
                        elif os.path.isdir(fp):
                            import shutil
                            shutil.rmtree(fp)
                    except Exception as e:
                        self.log(f"Error removing {fp}: {e}")
        
        # Clean up .part files and empty subtitle files in the output directory
        out_dir = self.out_entry.get().strip() if self.out_entry.get().strip() else os.path.join(os.getcwd(), "out_dir")
        if os.path.exists(out_dir):
            self.cleanup_part_files(out_dir)
            self.cleanup_empty_subtitle_files(out_dir)
        
        self.log("Stopped and cleaned logs/temp/part files/empty subtitles.")

    def browse_out(self):
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.out_entry.delete(0, tk.END)
            self.out_entry.insert(0, path)

    def browse_cookies(self):
        path = filedialog.askopenfilename(title="Select cookies.txt", filetypes=[("Text Files", "*.txt")])
        if path:
            self.cookies_path.set(path)

    def log(self, msg):
        # Prefer logging to progress window if it exists, otherwise to main log
        target = getattr(self, 'progress_text', None)
        if not target:
            target = getattr(self, 'main_status_text', None)
        if not target:
            return
        target.config(state="normal")
        target.insert(tk.END, msg + "\n")
        target.see(tk.END)
        target.config(state="disabled")
        try:
            self.root.update()
        except Exception:
            pass

    def stop_only(self):
        # Signal stop if running
        if hasattr(self, 'stop_event') and self.stop_event:
            self.stop_event.set()
        # Terminate all running ffmpeg processes
        for proc in getattr(self, 'ffmpeg_processes', []):
            try:
                if proc.poll() is None:
                    proc.terminate()
                    self.log("Terminated ffmpeg process.")
            except Exception as e:
                self.log(f"Error terminating ffmpeg: {e}")
        self.ffmpeg_processes = []
        self.log("Stopped process.")

    def close_progress_window(self):
        if hasattr(self, 'progress_win') and self.progress_win:
            try:
                if self.progress_win.winfo_exists():
                    self.progress_win.destroy()
            except Exception:
                pass
        # Clear references so future runs can recreate cleanly
        self.progress_win = None
        if hasattr(self, 'progress_text'):
            self.progress_text = None

    def start_decrypt_combine_only(self):
        """Start decrypt and combine process for already downloaded files"""
        import threading
        from tkinter import messagebox
        
        # Check if a process is already running
        if hasattr(self, 'progress_win') and self.progress_win:
            try:
                if self.progress_win.winfo_exists():
                    messagebox.showwarning("Process Running", "Another process is already running. Please wait or stop it first.")
                    return
            except Exception:
                pass
        
        if hasattr(self, 'process_thread') and self.process_thread and self.process_thread.is_alive():
            messagebox.showwarning("Process Running", "Another process is already running. Please wait or stop it first.")
            return
        
        # Validate required fields
        decryption_key = self.decryption_key_entry.get().strip()
        out_dir = self.out_entry.get().strip()
        
        if not out_dir:
            out_dir = os.path.join(os.getcwd(), "out_dir")
        
        if not os.path.exists(out_dir):
            messagebox.showerror("Directory Not Found", f"Output directory does not exist: {out_dir}")
            return
        
        # Check if there are any encrypted files
        has_encrypted = self.has_encrypted_files(out_dir)
        
        if not has_encrypted and not decryption_key:
            # No encrypted files, but we can still combine non-encrypted video/audio pairs
            response = messagebox.askyesno(
                "No Encrypted Files", 
                "No encrypted files detected. Do you want to combine and rename video/audio files?"
            )
            if not response:
                return
        elif has_encrypted and not decryption_key:
            messagebox.showerror(
                "Decryption Key Required",
                "Encrypted files detected but no decryption key provided. Please enter the DRM decryption key."
            )
            return
        
        # Create progress window
        self._create_progress_window()
        
        self.stop_event = threading.Event()
        self.process_thread = threading.Thread(target=self._run_decrypt_combine_only, daemon=True)
        self.process_thread.start()
    
    def _run_decrypt_combine_only(self):
        """Run the decrypt and combine process"""
        try:
            decryption_key = self.decryption_key_entry.get().strip()
            out_dir = self.out_entry.get().strip() if self.out_entry.get().strip() else os.path.join(os.getcwd(), "out_dir")
            
            self.log("=" * 60)
            self.log("Starting Decrypt & Combine Process")
            self.log("=" * 60)
            self.log(f"Output directory: {out_dir}")
            
            # Update progress
            if hasattr(self, 'progress_label'):
                self.progress_label.config(text="Scanning for encrypted files...")
            
            # Step 1: Decrypt if needed
            encrypted_media_present = self.has_encrypted_files(out_dir)
            
            if encrypted_media_present:
                if decryption_key:
                    if self.stop_event.is_set():
                        self.log("Process stopped by user.")
                        return
                    
                    self.log("\n[Step 1/3] Decrypting encrypted files...")
                    if hasattr(self, 'progress_label'):
                        self.progress_label.config(text="Decrypting files...")
                    self.decrypt_files(decryption_key, out_dir)
                else:
                    self.log("ERROR: Encrypted files found but no decryption key provided!")
                    messagebox.showerror("Error", "Encrypted files found but no decryption key provided!")
                    return
            else:
                self.log("\n[Step 1/3] No encrypted files detected, skipping decryption.")
            
            # Step 2: Combine and rename
            if self.stop_event.is_set():
                self.log("Process stopped by user.")
                return
            
            self.log("\n[Step 2/3] Combining audio/video and renaming files...")
            if hasattr(self, 'progress_label'):
                self.progress_label.config(text="Combining and renaming files...")
            self.combine_files(out_dir)
            
            # Step 3: Cleanup
            if self.stop_event.is_set():
                self.log("Process stopped by user.")
                return
            
            self.log("\n[Step 3/3] Cleaning up temporary files...")
            if hasattr(self, 'progress_label'):
                self.progress_label.config(text="Cleaning up...")
            self.cleanup_temp_folders(out_dir)
            self.cleanup_part_files(out_dir)
            self.cleanup_empty_subtitle_files(out_dir)
            
            self.log("\n" + "=" * 60)
            self.log("Decrypt & Combine Process Completed Successfully!")
            self.log("=" * 60)
            
            if hasattr(self, 'progress_label'):
                self.progress_label.config(text="Process completed!")
            if hasattr(self, 'progress_bar'):
                self.progress_bar['value'] = 100
            
            messagebox.showinfo("Success", "Decrypt and combine process completed successfully!")
            
        except Exception as e:
            self.log(f"\nERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        finally:
            try:
                self.close_progress_window()
            except Exception:
                pass
    
    def _create_progress_window(self):
        """Create the progress window (extracted for reuse)"""
        self.progress_win = tk.Toplevel(self.root)
        self.progress_win.title("Progress Log")
        try:
            sw = self.progress_win.winfo_screenwidth()
            sh = self.progress_win.winfo_screenheight()
        except Exception:
            sw, sh = 1024, 768
        pw = max(520, min(760, sw - 160))
        ph = max(320, min(480, sh - 200))
        self.progress_win.geometry(f"{pw}x{ph}+120+80")
        self.progress_win.minsize(480, 300)
        self.progress_win.resizable(True, True)
        self.progress_win.configure(bg="#6D4C41")
        self.progress_win.protocol("WM_DELETE_WINDOW", self.close_progress_window)
        
        # Status log in progress window
        self.progress_text = tk.Text(self.progress_win, height=15, width=80, state="disabled", bg="#A1887F", fg="#4E342E", font=("Consolas", 11), relief="flat")
        self.progress_text.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        self.status_text = self.progress_text

        # Progress bar
        import tkinter.ttk as ttk
        s = ttk.Style()
        s.theme_use('clam')
        s.configure("TProgressbar", thickness=25, troughcolor="#6D4C41", background="#D84315", darkcolor="#D84315", lightcolor="#D84315", bordercolor="#6D4C41")
        self.progress_bar = ttk.Progressbar(self.progress_win, orient="horizontal", length=500, mode="determinate", style="TProgressbar")
        self.progress_bar.pack(pady=(0, 5), padx=16, fill="x")

        # Progress label
        self.progress_label = tk.Label(self.progress_win, text="Initializing...", bg="#6D4C41", fg="#FFCCBC", font=("Segoe UI", 11, "bold"))
        self.progress_label.pack(pady=(0, 10))
        
        # Stop button
        stop_btn = tk.Button(self.progress_win, text="Stop", command=self.stop_only, bg="#B71C1C", fg="#FFF8E1", font=("Segoe UI", 12, "bold"), relief="flat")
        stop_btn.pack(pady=(0, 16))

    def start_full_process(self):
        import threading
        # If a progress window already exists and is open, raise it and do not create another
        if hasattr(self, 'progress_win') and self.progress_win:
            try:
                if self.progress_win.winfo_exists():
                    try:
                        self.progress_win.deiconify()
                        self.progress_win.lift()
                        self.progress_win.focus_force()
                    except Exception:
                        pass
                    self.log("A process is already in progress (or a log window is open).")
                    return
            except Exception:
                pass
        if hasattr(self, 'process_thread') and self.process_thread and self.process_thread.is_alive():
            self.log("A process is already running. Please wait or stop it first.")
            return
        # Create progress window
        self._create_progress_window()
        self.stop_event = threading.Event()
        self.process_thread = threading.Thread(target=self._run_full_process, daemon=True)
        self.process_thread.start()

        # Initialize progress variables
        self.total_lectures = 0
        self.completed_lectures = 0

    def _run_full_process(self):
        try:
            self.save_config()
            course_url = self.course_url_entry.get().strip()
            token = self.token_entry.get().strip()
            chapter = self.chapter_entry.get().strip()
            lecture = self.lecture_entry.get().strip()
            quality = self.quality_entry.get().strip()
            lang = self.lang_var.get().strip()
            
            # Convert connection speed to concurrent downloads value
            speed = self.connection_speed.get()
            if speed == "slow":
                concurrent = "3"
            elif speed == "fast":
                concurrent = "25"
            else:  # medium (default)
                concurrent = "10"
            
            out_dir = self.out_entry.get().strip()
            loglevel = self.loglevel_entry.get().strip()
            browser = self.browser_entry.get().strip()
            h265_crf = self.h265_crf_entry.get().strip()
            h265_preset = self.h265_preset_entry.get().strip()
            import threading, queue
            # one save is enough
            decryption_key = self.decryption_key_entry.get().strip()

            if not course_url or not token:
                self.log("Course URL and Access Token are required.")
                messagebox.showerror("Input Error", "Course URL and Access Token are required.")
                return

            # Parse chapters
            chapters = []
            if chapter:
                for part in chapter.split(','):
                    if '-' in part:
                        try:
                            start, end = part.split('-')
                            start = int(start.strip())
                            end = int(end.strip())
                            chapters.extend(list(range(start, end+1)))
                        except Exception:
                            continue
                    else:
                        try:
                            chapters.append(int(part.strip()))
                        except Exception:
                            continue
            else:
                chapters = [None]  # Download all if not specified

            search_base = out_dir if out_dir else os.path.join(os.getcwd(), "out_dir")

            for chap in chapters:
                if self.stop_event.is_set():
                    self.log("Stopped before chapter download.")
                    return
                self.log(f"Starting download for chapter: {chap if chap else 'ALL'}...")
                download_cmd = [sys.executable, "main.py", "--course-url", course_url, "--bearer", token]
                if chap:
                    download_cmd += ["--chapter", str(chap)]
                if lecture:
                    download_cmd += ["--lecture", lecture]
                if quality:
                    download_cmd += ["--quality", quality]
                # Only add --download-captions and -l <lang> if Download Captions is checked
                if self.download_captions.get():
                    download_cmd.append("--download-captions")
                    if lang:
                        download_cmd += ["-l", lang]
                if concurrent:
                    download_cmd += ["--concurrent-downloads", concurrent]
                if out_dir:
                    download_cmd += ["--out", out_dir]
                if loglevel:
                    download_cmd += ["--log-level", loglevel]
                if browser:
                    download_cmd += ["--browser", browser]
                if self.use_h265.get():
                    download_cmd.append("--use-h265")
                if self.use_nvenc.get():
                    download_cmd.append("--use-nvenc")
                if self.download_captions.get():
                    download_cmd.append("--download-captions")
                if self.download_assets.get():
                    download_cmd.append("--download-assets")
                if self.download_quizzes.get():
                    download_cmd.append("--download-quizzes")
                if self.keep_vtt.get():
                    download_cmd.append("--keep-vtt")
                if self.skip_lectures.get():
                    download_cmd.append("--skip-lectures")
                if self.skip_hls.get():
                    download_cmd.append("--skip-hls")
                if self.info.get():
                    download_cmd.append("--info")
                if self.id_as_course_name.get():
                    download_cmd.append("--id-as-course-name")
                if self.subscription_course.get():
                    download_cmd.append("--subscription-course")
                if self.save_to_file.get():
                    download_cmd.append("--save-to-file")
                if self.load_from_file.get():
                    download_cmd.append("--load-from-file")
                if self.continue_lecture_numbers.get():
                    download_cmd.append("--continue-lecture-numbers")
                if h265_crf:
                    download_cmd += ["--h265-crf", h265_crf]
                if h265_preset:
                    download_cmd += ["--h265-preset", h265_preset]

                # Pass --no-report to main.py so we can generate it after our own cleanup
                download_cmd.append("--no-report")

                # Set decryption key in environment for main.py to use
                env = os.environ.copy()
                if decryption_key:
                    env["UDEMY_DECRYPTION_KEY"] = decryption_key

                self.log(f"Running: {' '.join(download_cmd)}")
                try:
                    proc = subprocess.Popen(
                        download_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=env
                    )
                    def enqueue_output(pipe, q, label):
                        for line in iter(pipe.readline, ''):
                            q.put((label, line))
                        pipe.close()

                    q = queue.Queue()
                    t_out = threading.Thread(target=enqueue_output, args=(proc.stdout, q, 'STDOUT'))
                    t_err = threading.Thread(target=enqueue_output, args=(proc.stderr, q, 'STDERR'))
                    t_out.start()
                    t_err.start()
                    
                    captured_lines = []

                    while True:
                        if self.stop_event.is_set():
                            proc.terminate()
                            self.log("Process terminated by user.")
                            break
                        try:
                            label, line = q.get(timeout=0.1)
                            if line:
                                stripped = line.strip()
                                self.log(stripped)
                                captured_lines.append(stripped)
                                if len(captured_lines) > 20:
                                    captured_lines.pop(0)
                        except queue.Empty:
                            if proc.poll() is not None:
                                break
                    t_out.join()
                    t_err.join()
                    if proc.returncode != 0:
                        self.log(f"Process exited with errors for chapter {chap}.")
                        error_details = "\n".join(captured_lines[-10:]) if captured_lines else "No output captured."
                        messagebox.showerror("Download Error", f"Download failed for chapter {chap}.\n\nLast output:\n{error_details}")
                        return
                except Exception as e:
                    self.log(f"Error running download for chapter {chap}: {e}")
                    return

                # Step 2: Decrypt (only when encrypted media exists)
                encrypted_media_present = self.has_encrypted_files(search_base)
                if encrypted_media_present:
                    if not decryption_key:
                        self.log("Encrypted media detected but no decryption key was provided. Aborting.")
                        messagebox.showerror(
                            "Decryption Key Required",
                            "Encrypted lectures were downloaded but no DRM decryption key was supplied."
                            " Please provide the key and try again.",
                        )
                        return
                    if self.stop_event.is_set():
                        self.log("Stopped before decryption.")
                        return
                    self.log(f"Starting decryption for chapter {chap if chap else 'ALL'}...")
                    self.decrypt_files(decryption_key, search_base)
                else:
                    self.log("No encrypted media found. Skipping decryption step.")

                # Step 3: Combine and rename (run for both encrypted and non-encrypted videos)
                if self.stop_event.is_set():
                    self.log("Stopped before combining.")
                    return
                self.log(f"Combining audio/video and renaming files for chapter {chap if chap else 'ALL'}...")
                self.combine_files(search_base)

                # Step 4: Clean up temp folders and part files
                if self.stop_event.is_set():
                    self.log("Stopped before final cleanup.")
                    return
                self.log(f"Cleaning up temporary directories, part files, and empty subtitle files for chapter {chap if chap else 'ALL'}...")
                self.cleanup_temp_folders(search_base)
                self.cleanup_part_files(search_base)
                self.cleanup_empty_subtitle_files(search_base)

            self.log("All chapters processed.")
            self.cleanup_temp_folders(search_base)
            self.cleanup_part_files(search_base)
            self.cleanup_empty_subtitle_files(search_base)
            self.log("All steps completed successfully!")
            
            # Mark as successful completion
            process_success = True
            
            # Generate verification report
            self.log("Generating final verification report...")
            try:
                from download_verifier import verify_course_downloads, generate_verification_report
                import webbrowser
                
                # Reload id_to_title_map
                id_to_title_map = {}
                for dirpath, _, filenames in os.walk(search_base):
                    if "id_to_title.json" in filenames:
                        map_file_path = os.path.join(dirpath, "id_to_title.json")
                        try:
                            with open(map_file_path, "r", encoding="utf-8") as f:
                                id_to_title_map = json.load(f)
                        except Exception:
                            pass
                        break
                
                final_results = verify_course_downloads(search_base, id_to_title_map)
                course_name = os.path.basename(search_base)
                html_report_path = generate_verification_report(search_base, course_name, final_results)
                
                if html_report_path and os.path.exists(html_report_path):
                    self.log(f"Verification report saved: {html_report_path}")
                    webbrowser.open('file://' + os.path.abspath(html_report_path))
            except Exception as e:
                self.log(f"Error generating report: {e}")
            
        except Exception as e:
            # Log the error and mark as failure
            self.log(f"ERROR: Process failed with exception: {str(e)}")
            import traceback
            self.log(f"Traceback:\n{traceback.format_exc()}")
            process_success = False
            
        finally:
            # Only close progress window on success, keep it open on failure so user can see logs
            if 'process_success' in locals() and process_success:
                self.log("\n✓ Process completed successfully! Closing log window in 3 seconds...")
                try:
                    self.root.after(3000, self.close_progress_window)  # Close after 3 seconds
                except Exception:
                    pass
            else:
                # On failure, keep window open and add message
                if hasattr(self, 'progress_win') and self.progress_win:
                    try:
                        self.log("\n" + "="*60)
                        self.log("⚠ Process completed with errors - Log window will stay open")
                        self.log("Please review the logs above to identify the issue")
                        self.log("You can close this window manually when done")
                        self.log("="*60)
                    except Exception:
                        pass

    def save_config(self):
        # Save all current options to config.json
        config = {
            "course_url": self.course_url_entry.get().strip(),
            "token": self.token_entry.get().strip(),
            "udemy_type": self.udemy_type_var.get(),
            "chapter": self.chapter_entry.get().strip(),
            "lecture": self.lecture_entry.get().strip(),
            "quality": self.quality_entry.get().strip(),
            "lang": self.lang_var.get().strip(),
            "connection_speed": self.connection_speed.get(),  # Save radio button selection instead of numeric value
            "out_dir": self.out_entry.get().strip(),
            "loglevel": self.loglevel_entry.get().strip(),
            "browser": self.browser_entry.get().strip(),
            "h265_crf": self.h265_crf_entry.get().strip(),
            "h265_preset": self.h265_preset_entry.get().strip(),
            "decryption_key": self.decryption_key_entry.get().strip(),
            "use_h265": self.use_h265.get(),
            "use_nvenc": self.use_nvenc.get(),
            "download_captions": self.download_captions.get(),
            "download_assets": self.download_assets.get(),
            "download_quizzes": self.download_quizzes.get(),
            "keep_vtt": self.keep_vtt.get(),
            "skip_lectures": self.skip_lectures.get(),
            "skip_hls": self.skip_hls.get(),
            "info": self.info.get(),
            "id_as_course_name": self.id_as_course_name.get(),
            "subscription_course": self.subscription_course.get(),
            "save_to_file": self.save_to_file.get(),
            "load_from_file": self.load_from_file.get(),
            "continue_lecture_numbers": self.continue_lecture_numbers.get(),
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log(f"Error saving config: {e}")

    def load_config(self):
        # Load last options from config.json
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            self.course_url_entry.insert(0, config.get("course_url", ""))
            self.token_entry.insert(0, config.get("token", ""))
            self.udemy_type_var.set(config.get("udemy_type", "normal"))
            self.chapter_entry.insert(0, config.get("chapter", ""))
            self.lecture_entry.insert(0, config.get("lecture", ""))
            self.quality_entry.set(config.get("quality", "720"))
            self.lang_var.set(config.get("lang", "ar+en"))
            
            # Load connection speed (backward compatible with old "concurrent" field)
            if "connection_speed" in config:
                self.connection_speed.set(config.get("connection_speed", "medium"))
            elif "concurrent" in config:
                # Convert old concurrent number to speed category for backward compatibility
                concurrent_val = config.get("concurrent", "10")
                try:
                    val = int(concurrent_val) if concurrent_val else 10
                    if val <= 5:
                        self.connection_speed.set("slow")
                    elif val >= 15:
                        self.connection_speed.set("fast")
                    else:
                        self.connection_speed.set("medium")
                except:
                    self.connection_speed.set("medium")
            else:
                self.connection_speed.set("medium")
            
            self.out_entry.insert(0, config.get("out_dir", ""))
            self.loglevel_entry.insert(0, config.get("loglevel", ""))
            self.browser_entry.insert(0, config.get("browser", ""))
            self.h265_crf_entry.insert(0, config.get("h265_crf", ""))
            self.h265_preset_entry.insert(0, config.get("h265_preset", ""))
            self.decryption_key_entry.insert(0, config.get("decryption_key", ""))
            self.use_h265.set(config.get("use_h265", False))
            self.use_nvenc.set(config.get("use_nvenc", False))
            self.download_captions.set(config.get("download_captions", False))
            self.download_assets.set(config.get("download_assets", False))
            self.download_quizzes.set(config.get("download_quizzes", False))
            self.keep_vtt.set(config.get("keep_vtt", False))
            self.skip_lectures.set(config.get("skip_lectures", False))
            self.skip_hls.set(config.get("skip_hls", False))
            self.info.set(config.get("info", False))
            self.id_as_course_name.set(config.get("id_as_course_name", False))
            self.subscription_course.set(config.get("subscription_course", False))
            self.save_to_file.set(config.get("save_to_file", False))
            self.load_from_file.set(config.get("load_from_file", False))
            self.continue_lecture_numbers.set(config.get("continue_lecture_numbers", False))
        except Exception as e:
            self.log(f"Error loading config: {e}")
        # Do NOT auto-run process on config load

    def has_encrypted_files(self, search_dir):
        """Check whether any encrypted video or audio segments exist under the search directory."""
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith((".encrypted.mp4", ".encrypted.m4a")):
                    return True
        return False

    def decrypt_files(self, decryption_key, search_dir):
        # Find all encrypted files and decrypt with correct output naming
        self.log(f"Starting decryption in directory: {search_dir}")
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".encrypted.mp4") or file.endswith(".encrypted.m4a"):
                    if self.stop_event.is_set():
                        self.log("Stopped during decryption.")
                        return
                    in_path = os.path.join(root, file)
                    base_name = file.replace(".encrypted", "")
                    out_path = os.path.join(root, base_name)
                    if os.path.exists(out_path):
                        self.log(f"Skipping already decrypted: {base_name}")
                        continue
                    cmd = [self.ffmpeg_path, "-nostdin", "-loglevel", "error", "-decryption_key", decryption_key, "-i", in_path, "-c", "copy", out_path]
                    self.log(f"Decrypting: {file} -> {base_name}")
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                        )
                        self.ffmpeg_processes.append(proc)
                        stdout, stderr = proc.communicate()
                        if stdout:
                            for line in stdout.splitlines():
                                self.log(line)
                        if stderr:
                            for line in stderr.splitlines():
                                self.log(f"[ffmpeg] {line}")
                        if self.stop_event.is_set():
                            self.log("Terminated ffmpeg during decryption.")
                            return
                        if proc.returncode != 0:
                            self.log(f"Error decrypting {file}: ffmpeg exited with code {proc.returncode}")
                        elif not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                            self.log(f"Decryption failed: Output file not created or empty for {file}")
                        else:
                            self.log(f"Decrypted: {out_path}")
                    except Exception as e:
                        self.log(f"Error running ffmpeg: {e}")

    def combine_files(self, search_dir):
        from pathvalidate import sanitize_filename
        final_suffix = ""
        id_to_title_map = {}

        # Find and load the ID-to-title map
        for dirpath, _, filenames in os.walk(search_dir):
            if "id_to_title.json" in filenames:
                map_file_path = os.path.join(dirpath, "id_to_title.json")
                try:
                    with open(map_file_path, "r", encoding="utf-8") as f:
                        id_to_title_map = json.load(f)
                    self.log(f"Loaded title mapping from {map_file_path}")
                except Exception as e:
                    self.log(f"Error loading title map: {e}")
                break # Assume one map per run

        self.log(f"Starting combination in directory: {search_dir}")
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                # Ensure we only process decrypted .mp4 files that are not still in their original encrypted form
                # and have not yet been combined (checked later by os.path.exists(final_output_path)).
                # This fixes the logical error when final_suffix is empty.
                if file.endswith(".mp4") and ".encrypted" not in file:
                    file_id = file[:-4]
                    mp4_path = os.path.join(root, file)
                    m4a_path = os.path.join(root, f"{file_id}.m4a")

                    # Determine final name
                    lecture_title = id_to_title_map.get(file_id)
                    if lecture_title:
                        final_base_name = sanitize_filename(lecture_title)
                        self.log(f"Found title for ID {file_id}: '{lecture_title}'")
                    else:
                        final_base_name = file_id
                        self.log(f"No title found for ID {file_id}, using ID as name.")

                    final_output_name = f"{final_base_name}{final_suffix}.mp4"
                    final_output_path = os.path.join(root, final_output_name)

                    if os.path.exists(mp4_path) and os.path.exists(m4a_path):
                        # Case 1: Both MP4 (video) and M4A (audio) exist - need to combine them
                        if os.path.exists(final_output_path):
                            self.log(f"Skipping already combined file: {final_output_name}")
                            continue

                        self.log(f"Combining and fixing sync for: {file}")
                        cmd = [self.ffmpeg_path, "-nostdin", "-loglevel", "error", "-i", mp4_path, "-i", m4a_path, "-copyts", "-start_at_zero", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy", "-shortest", final_output_path]
                        try:
                            proc = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                            )
                            self.ffmpeg_processes.append(proc)
                            stdout, stderr = proc.communicate()
                            if proc.returncode == 0 and os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                                self.log(f"  > Success! Cleaning up temporary files.")
                                # Clean up decrypted and encrypted files
                                encrypted_mp4_path = os.path.join(root, f"{file_id}.encrypted.mp4")
                                encrypted_m4a_path = os.path.join(root, f"{file_id}.encrypted.m4a")
                                
                                # Backup to trash instead of delete
                                trash_dir = os.path.join(root, "_trash")
                                os.makedirs(trash_dir, exist_ok=True)

                                for f_path in [mp4_path, m4a_path, encrypted_mp4_path, encrypted_m4a_path]:
                                    if os.path.exists(f_path):
                                        try:
                                            shutil.move(f_path, os.path.join(trash_dir, os.path.basename(f_path)))
                                        except Exception as e:
                                            self.log(f"Error moving {f_path} to trash: {e}")
                                
                                # Clean up potential .tmp files
                                tmp_file = f"{final_output_path}.tmp"
                                if os.path.exists(tmp_file):
                                    try:
                                        os.remove(tmp_file)
                                        self.log(f"Removed temp file: {os.path.basename(tmp_file)}")
                                    except Exception:
                                        pass
                                self.log(f"Combined: {final_output_path}")

                                # Rename associated subtitle files
                                self._rename_subtitles(root, file_id, final_base_name, final_suffix)
                            else:
                                self.log(f"  > ERROR: ffmpeg failed to combine {file}. Temporary files were NOT deleted.")
                                if stderr:
                                    for line in stderr.splitlines():
                                        self.log(f"[ffmpeg] {line}")
                        except Exception as e:
                            self.log(f"Error running ffmpeg: {e}")
                    elif os.path.exists(mp4_path) and lecture_title:
                        # Case 2: Only MP4 exists (already has audio muxed) - just rename it
                        if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
                            self.log(f"Skipping already renamed file: {final_output_name}")
                            # Still clean up the numeric ID file if final exists
                            if mp4_path != final_output_path:
                                try:
                                    # Backup to trash instead of delete
                                    trash_dir = os.path.join(root, "_trash")
                                    os.makedirs(trash_dir, exist_ok=True)
                                    shutil.move(mp4_path, os.path.join(trash_dir, os.path.basename(mp4_path)))
                                except Exception:
                                    pass
                            continue

                        # Check if file is just a numeric ID that needs renaming
                        if file_id.isdigit() and file_id in id_to_title_map:
                            self.log(f"Renaming single MP4 file: {file} -> {final_output_name}")
                            try:
                                os.rename(mp4_path, final_output_path)
                                self.log(f"Renamed: {final_output_path}")
                                
                                # Clean up potential .tmp files
                                tmp_file = f"{final_output_path}.tmp"
                                if os.path.exists(tmp_file):
                                    try:
                                        os.remove(tmp_file)
                                        self.log(f"Removed temp file: {os.path.basename(tmp_file)}")
                                    except Exception:
                                        pass
                                
                                # Rename associated subtitle files
                                self._rename_subtitles(root, file_id, final_base_name, final_suffix)
                            except Exception as e:
                                self.log(f"Error renaming {file}: {e}")
                    else:
                        # File doesn't need processing (already has proper name or no title mapping)
                        if not lecture_title and file_id.isdigit():
                            self.log(f"Skipping {file} - no title mapping found for ID {file_id}")

    def _rename_subtitles(self, root_dir, file_id, final_base_name, final_suffix):
        """Helper function to rename subtitle files associated with a lecture"""
        try:
            # Find subtitle files that start with the file_id
            for srt_file in os.listdir(root_dir):
                if srt_file.startswith(file_id) and srt_file.endswith(".srt"):
                    # Extract language suffix if present (e.g., _en.srt, _ar.srt)
                    lang_part_match = re.search(r'(_[a-z]{2,3}(?:_[A-Z]{2,3})?).srt$', srt_file)
                    if lang_part_match:
                        lang_part = lang_part_match.group(1)
                        old_srt_path = os.path.join(root_dir, srt_file)
                        new_srt_name = f"{final_base_name}{final_suffix}{lang_part}.srt"
                        new_srt_path = os.path.join(root_dir, new_srt_name)
                        if not os.path.exists(new_srt_path):
                            os.rename(old_srt_path, new_srt_path)
                            self.log(f"Renamed caption: {srt_file} -> {new_srt_name}")
        except Exception as e:
            self.log(f"Error renaming subtitles for {file_id}: {e}")

    def cleanup_temp_folders(self, search_dir):
        self.log(f"Scanning for 'temp' folders in {search_dir}...")
        for root, dirs, files in os.walk(search_dir):
            if 'temp' in dirs:
                temp_path = os.path.join(root, 'temp')
                try:
                    shutil.rmtree(temp_path)
                    self.log(f"Removed temporary directory: {temp_path}")
                except Exception as e:
                    self.log(f"Error removing temp directory {temp_path}: {e}")
    
    def cleanup_part_files(self, search_dir):
        """Clean up .part and .part.frag.urls files in the search directory"""
        self.log(f"Cleaning up .part files in {search_dir}...")
        try:
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.part'):
                        part_file_path = os.path.join(root, file)
                        
                        # Remove empty .part files - they indicate failed downloads
                        if os.path.getsize(part_file_path) == 0:
                            self.log(f"Removing empty .part file: {file}")
                            try:
                                os.remove(part_file_path)
                            except Exception as e:
                                self.log(f"Could not remove empty .part file {file}: {e}")
                            continue
                        
                        # Try to rename non-empty .part files to their proper names
                        base_name = file[:-5]  # Remove '.part' from the end
                        target_file_path = os.path.join(root, base_name)
                        
                        should_rename = False
                        if not os.path.exists(target_file_path):
                            should_rename = True
                        elif os.path.getsize(part_file_path) > os.path.getsize(target_file_path):
                            should_rename = True
                        
                        if should_rename:
                            self.log(f"Renaming .part file: {file} -> {base_name}")
                            if os.path.exists(target_file_path):
                                os.remove(target_file_path)
                            os.rename(part_file_path, target_file_path)
                            
                    elif file.endswith('.part.frag.urls'):
                        # Remove .part.frag.urls files
                        frag_urls_path = os.path.join(root, file)
                        self.log(f"Removing .part.frag.urls file: {file}")
                        try:
                            os.remove(frag_urls_path)
                        except Exception as e:
                            self.log(f"Could not remove {file}: {e}")
                            
        except Exception as e:
            self.log(f"Error cleaning up .part files in {search_dir}: {e}")
    
    def cleanup_empty_subtitle_files(self, search_dir):
        """Clean up empty subtitle files (.srt, .vtt) that were created during failed downloads"""
        self.log(f"Cleaning up empty subtitle files in {search_dir}...")
        try:
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith(('.srt', '.vtt')):
                        file_path = os.path.join(root, file)
                        if os.path.getsize(file_path) == 0:
                            self.log(f"Removing empty subtitle file: {file}")
                            try:
                                os.remove(file_path)
                            except Exception as e:
                                self.log(f"Could not remove empty subtitle file {file}: {e}")
        except Exception as e:
            self.log(f"Error cleaning up empty subtitle files in {search_dir}: {e}")
    
    def verify_downloads(self):
        """Verify downloads for a selected course directory"""
        from tkinter import messagebox, filedialog
        from download_verifier import load_id_to_title_map, verify_course_downloads, generate_verification_report
        import webbrowser
        
        # Ask user to select course directory
        course_dir = filedialog.askdirectory(
            title="Select Course Directory to Verify",
            initialdir=self.out_entry.get().strip() if self.out_entry.get().strip() else os.getcwd()
        )
        
        if not course_dir:
            return
        
        self.log(f"Verifying downloads in: {course_dir}")
        
        try:
            # Load the manifest
            id_to_title_map = load_id_to_title_map(course_dir)
            
            if not id_to_title_map:
                messagebox.showerror(
                    "Verification Failed",
                    f"Could not find id_to_title.json in {course_dir}\n\n"
                    "This file is created during the download process and is required for verification."
                )
                self.log("ERROR: id_to_title.json not found")
                return
            
            self.log(f"Found manifest with {len(id_to_title_map)} lectures")
            self.log("Running verification...")
            
            # Run verification
            results = verify_course_downloads(course_dir, id_to_title_map)
            
            # Generate HTML report (primary) and JSON report
            course_name = os.path.basename(course_dir)
            report_path = generate_verification_report(course_dir, course_name, results)
            
            # Show results to user
            self.show_verification_report(results, report_path)
            
            # Auto-open HTML report in browser
            if report_path and os.path.exists(report_path):
                self.log(f"Opening verification report in browser...")
                try:
                    webbrowser.open('file://' + os.path.abspath(report_path))
                except Exception as e:
                    self.log(f"Could not open browser: {e}")
            
        except Exception as e:
            self.log(f"ERROR during verification: {e}")
            messagebox.showerror("Verification Error", f"An error occurred during verification:\n\n{str(e)}")

    
    def show_verification_report(self, results: dict, report_path: str):
        """Display verification results in a dialog"""
        from tkinter import messagebox
        
        total = len(results['complete']) + len(results['incomplete']) + \
                len(results['missing']) + len(results['encrypted_pending'])
        
        complete_count = len(results['complete'])
        incomplete_count = len(results['incomplete'])
        missing_count = len(results['missing'])
        encrypted_count = len(results['encrypted_pending'])
        
        success_rate = (complete_count / total * 100) if total > 0 else 0
        
        # Build message
        message = f"Verification Complete!\n\n"
        message += f"Total Lectures: {total}\n"
        message += f"✓ Complete: {complete_count}\n"
        message += f"⚠ Encrypted (pending): {encrypted_count}\n"
        message += f"✗ Incomplete: {incomplete_count}\n"
        message += f"✗ Missing: {missing_count}\n\n"
        message += f"Success Rate: {success_rate:.1f}%\n\n"
        
        if report_path:
            message += f"Detailed report saved to:\n{report_path}"
        
        # Log details
        self.log("\n" + "="*60)
        self.log("VERIFICATION RESULTS")
        self.log("="*60)
        self.log(f"Complete: {complete_count}")
        self.log(f"Encrypted Pending: {encrypted_count}")
        self.log(f"Incomplete: {incomplete_count}")
        self.log(f"Missing: {missing_count}")
        self.log("="*60 + "\n")
        
        if incomplete_count > 0:
            self.log("Incomplete files:")
            for item in results['incomplete'][:10]:  # Show first 10
                self.log(f"  - {item['title']}: {item['reason']}")
            if len(results['incomplete']) > 10:
                self.log(f"  ... and {len(results['incomplete']) - 10} more")
        
        if missing_count > 0:
            self.log("Missing files:")
            for item in results['missing'][:10]:  # Show first 10
                self.log(f"  - {item['title']}")
            if len(results['missing']) > 10:
                self.log(f"  ... and {len(results['missing']) - 10} more")
        
        # Show dialog
        if incomplete_count > 0 or missing_count > 0:
            messagebox.showwarning("Verification Complete - Issues Found", message)
        else:
            messagebox.showinfo("Verification Complete - All Good!", message)

def main():
    root = tk.Tk()
    app = UdemyDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
