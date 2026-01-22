import os
import random
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import sys
import pygame
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from scraperHelpers import check_stock_zara, check_stock_bershka, check_stock_mango, \
    check_stock_pull_and_bear

load_dotenv()
DEFAULT_BOT_API = os.getenv("BOT_API", "")
DEFAULT_CHAT_ID = os.getenv("CHAT_ID", "")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def play_sound(sound_file, log_func=None):
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(sound_file)
        pygame.mixer.music.play()
    except Exception as e:
        if log_func:
            log_func(f"Sound error: {e}")
        else:
            print(f"Sound error: {e}")

# This fcn is for sending messages
def send_telegram_message(message, bot_api, chat_id, log_func=None):
    if not bot_api or not chat_id:
        if log_func:
            log_func("Telegram message skipped (missing BOT_API or CHAT_ID).")
        else:
            print("Telegram message skipped (missing BOT_API or CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{bot_api}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        if log_func:
            log_func("Telegram message sent.")
        else:
            print("Telegram message sent.")
    except requests.exceptions.RequestException as e:
        if log_func:
            log_func(f"Failed to send Telegram message: {e}")
        else:
            print(f"Failed to send Telegram message: {e}")

class ZaraStockCheckerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Zara Stock Checker")
        self.root.geometry("600x650")

        self.running = False
        self.thread = None

        # URL and Store input
        tk.Label(root, text="URL:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.url_entry = tk.Entry(root, width=50)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(root, text="Store:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.store_var = tk.StringVar(value="zara")
        self.store_combo = ttk.Combobox(root, textvariable=self.store_var, values=["zara", "bershka", "mango", "pullbear"])
        self.store_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        self.add_button = tk.Button(root, text="Add URL", command=self.add_url)
        self.add_button.grid(row=1, column=1, padx=5, pady=5, sticky="e")

        # URL Listbox
        self.url_listbox = tk.Listbox(root, width=70, height=8)
        self.url_listbox.grid(row=2, column=0, columnspan=2, padx=5, pady=5)
        self.urls_data = []

        self.remove_button = tk.Button(root, text="Remove Selected", command=self.remove_url)
        self.remove_button.grid(row=3, column=0, columnspan=2, padx=5, pady=2)

        # Sizes
        tk.Label(root, text="Sizes (comma separated):").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.sizes_entry = tk.Entry(root, width=30)
        self.sizes_entry.insert(0, "36, XS")
        self.sizes_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Sleep times
        tk.Label(root, text="Min Sleep (s):").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        self.min_sleep_entry = tk.Entry(root, width=10)
        self.min_sleep_entry.insert(0, "500")
        self.min_sleep_entry.grid(row=5, column=1, padx=5, pady=5, sticky="w")

        tk.Label(root, text="Max Sleep (s):").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        self.max_sleep_entry = tk.Entry(root, width=10)
        self.max_sleep_entry.insert(0, "800")
        self.max_sleep_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w")

        # Telegram Settings
        tk.Label(root, text="Telegram Bot API:").grid(row=7, column=0, padx=5, pady=5, sticky="e")
        self.bot_api_entry = tk.Entry(root, width=50)
        self.bot_api_entry.insert(0, DEFAULT_BOT_API)
        self.bot_api_entry.grid(row=7, column=1, padx=5, pady=5, sticky="w")

        tk.Label(root, text="Telegram Chat ID:").grid(row=8, column=0, padx=5, pady=5, sticky="e")
        self.chat_id_entry = tk.Entry(root, width=30)
        self.chat_id_entry.insert(0, DEFAULT_CHAT_ID)
        self.chat_id_entry.grid(row=8, column=1, padx=5, pady=5, sticky="w")

        # Controls
        self.start_button = tk.Button(root, text="Start Checker", command=self.start_checker, bg="green", fg="white")
        self.start_button.grid(row=9, column=0, pady=10)

        self.stop_button = tk.Button(root, text="Stop Checker", command=self.stop_checker, bg="red", fg="white", state=tk.DISABLED)
        self.stop_button.grid(row=9, column=1, pady=10)

        # Handle window close
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Log Area
        tk.Label(root, text="Logs:").grid(row=10, column=0, padx=5, sticky="w")
        self.log_area = scrolledtext.ScrolledText(root, width=70, height=8, state=tk.DISABLED)
        self.log_area.grid(row=11, column=0, columnspan=2, padx=5, pady=5)

        self.driver = None

        if not DEFAULT_BOT_API or not DEFAULT_CHAT_ID:
            self.log("Telegram configuration missing. Please fill in Bot API and Chat ID.")

    def log(self, message):
        """Thread-safe logging to the GUI and console."""
        print(message)  # Still print to console for debugging
        def append():
            self.log_area.config(state=tk.NORMAL)
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
        self.root.after(0, append)

    def add_url(self):
        url = self.url_entry.get().strip()
        store = self.store_var.get()
        if url:
            self.urls_data.append({"url": url, "store": store})
            self.url_listbox.insert(tk.END, f"[{store}] {url}")
            self.url_entry.delete(0, tk.END)
        else:
            messagebox.showwarning("Warning", "Please enter a URL")

    def remove_url(self):
        selected = self.url_listbox.curselection()
        if selected:
            idx = selected[0]
            self.url_listbox.delete(idx)
            del self.urls_data[idx]

    def start_checker(self):
        if not self.urls_data:
            messagebox.showwarning("Warning", "Please add at least one URL")
            return
        
        try:
            self.min_sleep = int(self.min_sleep_entry.get())
            self.max_sleep = int(self.max_sleep_entry.get())
            self.sizes_to_check = [s.strip() for s in self.sizes_entry.get().split(",")]
            self.bot_api = self.bot_api_entry.get().strip()
            self.chat_id = self.chat_id_entry.get().strip()
        except ValueError:
            messagebox.showerror("Error", "Invalid sleep time values")
            return

        self.log("Starting checker...")
        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        self.thread = threading.Thread(target=self.run_bot, daemon=True)
        self.thread.start()

    def stop_checker(self):
        self.running = False
        self.log("Stopping... (will stop after current check finishes)")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def on_closing(self):
        """Clean up resources before closing the application."""
        self.running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.root.destroy()

    def run_bot(self):
        cart_status = {item["url"]: False for item in self.urls_data}
        
        while self.running:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )

            try:
                service = Service()
                service.creation_flags = subprocess.CREATE_NO_WINDOW
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                self.log(f"Failed to initialize driver: {e}")
                time.sleep(10)
                continue

            try:
                for item in self.urls_data:
                    if not self.running: break
                    try:
                        url = item["url"]
                        store = item["store"]
                        
                        if cart_status.get(url):
                            self.log(f"Item {url} already flagged, skipping...")
                            continue
                        
                        self.driver.get(url)
                        self.log("--------------------------------")
                        self.log(f"Checking URL: {url} ({store})")
                        
                        size_in_stock = None
                        if store == "zara":
                            size_in_stock = check_stock_zara(self.driver, self.sizes_to_check)
                        elif store == "bershka":
                            size_in_stock = check_stock_bershka(self.driver, self.sizes_to_check)
                        elif store == "mango":
                            size_in_stock = check_stock_mango(self.driver, self.sizes_to_check)
                        elif store == "pullbear":
                            size_in_stock = check_stock_pull_and_bear(self.driver, self.sizes_to_check)
                        
                        if size_in_stock:
                            message = f"🛍️{size_in_stock} beden stokta!!!!\nLink: {url}"
                            self.log(f"UYARI: {message}")
                            play_sound(resource_path('Crystal.mp3'))
                            send_telegram_message(message, self.bot_api, self.chat_id, log_func=self.log)
                            # cart_status[url] = True # Uncomment if you want to stop checking after found
                        else:
                            self.log(f"{url} checked - no stock.")
                            
                    except Exception as e:
                        self.log(f"Error with URL {item.get('url')}: {e}")
            finally:
                if self.driver:
                    self.driver.quit()
                    self.driver = None

            if not self.running: break
            
            sleep_time = random.randint(self.min_sleep, self.max_sleep)
            self.log(f"Sleeping for {sleep_time // 60} minutes and {sleep_time % 60} seconds...")
            
            # Sleep in small increments to remain responsive to stop command
            for _ in range(sleep_time):
                if not self.running: break
                time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = ZaraStockCheckerGUI(root)
    root.mainloop()
