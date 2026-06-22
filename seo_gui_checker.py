import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
import pandas as pd
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

GOLD = "#D4AF37"
GOLD_DARK = "#9C7A18"
BG = "#0D0D0D"
CARD = "#171717"
TEXT = "#F5F5F5"
MUTED = "#A3A3A3"

TEST_PARAMS = [
    "?ref=online-casino",
    "?ref=porno-izle",
    "?ref=film-indir",
    "?utm_source=casino",
    "?s=online-casino"
]

SPAM_WORDS = [
    "casino", "bet", "bahis", "porno", "escort",
    "film indir", "slot", "poker", "adult"
]

# Gerçek bir tarayıcı gibi görünmek için başlıklar genişletildi
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}


def clean_url(url):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path.rstrip("/") or "/",
        "",
        "",
        ""
    ))


def get_page(url):
    try:
        # SSL hatalarını yoksaymak ve takılmamak için verify=False eklenebilir (Tercihe bağlı)
        return requests.get(
            url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True,
            verify=True 
        )
    except Exception as e:
        return f"Hata: {str(e)}"


def analyze_url(base_url, test_url):
    r = get_page(test_url)

    result = {
        "base_url": base_url,
        "test_url": test_url,
        "status": "",
        "final_url": "",
        "risk": "UNKNOWN",
        "meta_robots": "",
        "x_robots_tag": "",
        "canonical": "",
        "canonical_ok": False,
        "spam_words": "",
        "notes": ""
    }

    if isinstance(r, str) or r is None:
        result["risk"] = "ERROR"
        result["notes"] = f"İstek başarısız: {r if isinstance(r, str) else 'Bağlantı Hatası'}"
        return result

    result["status"] = r.status_code
    result["final_url"] = r.url
    result["x_robots_tag"] = r.headers.get("X-Robots-Tag", "")

    content_type = r.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        result["risk"] = "LOW"
        result["notes"] = f"HTML değil: {content_type}"
        return result

    try:
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        result["risk"] = "ERROR"
        result["notes"] = f"HTML Parse Hatası: {str(e)}"
        return result

    robots = soup.find(
        "meta",
        attrs={"name": lambda x: x and x.lower() == "robots"}
    )
    if robots:
        result["meta_robots"] = robots.get("content", "")

    canonical = soup.find("link", rel=lambda x: x and "canonical" in x.lower())
    if canonical:
        result["canonical"] = canonical.get("href", "")

    page_text = soup.get_text(" ", strip=True).lower()
    found_words = [w for w in SPAM_WORDS if w in page_text]
    result["spam_words"] = ", ".join(found_words)

    noindex_found = (
        "noindex" in (result["meta_robots"] or "").lower()
        or "noindex" in (result["x_robots_tag"] or "").lower()
    )

    canonical_clean = clean_url(result["canonical"]) if result["canonical"] else ""
    base_clean = clean_url(base_url)
    result["canonical_ok"] = (canonical_clean == base_clean) if canonical_clean else False

    # Risk Mantığı Kararlılık İyileştirmesi
    if r.status_code != 200:
        result["risk"] = "LOW"
        result["notes"] = f"Sayfa {r.status_code} dönüyor, indekslenme riski düşük."
    elif found_words:
        result["risk"] = "HIGH"
        result["notes"] = f"Tehlike! Sayfada spam kelime bulundu: {result['spam_words']}"
    elif not noindex_found and not result["canonical_ok"]:
        result["risk"] = "HIGH"
        result["notes"] = "200 OK, noindex yok ve canonical ana URL'ye dönmüyor!"
    elif not noindex_found and result["canonical_ok"]:
        result["risk"] = "MEDIUM"
        result["notes"] = "Noindex yok ama canonical doğru (Parametreyi engelleyebilir)."
    elif noindex_found:
        result["risk"] = "LOW"
        result["notes"] = "Noindex bulundu, arama motorları indekslemeyecektir."
    else:
        result["risk"] = "LOW"
        result["notes"] = "İndeks riski düşük görünüyor."

    return result


class SeoCheckerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SEO Parametre Risk Kontrol Aracı")
        self.geometry("1250x760")
        self.configure(fg_color=BG)

        self.results = []
        self.running = False
        self.stop_requested = False  # İptal butonu için kontrol flag'i

        self.build_ui()

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=310, fg_color=CARD, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="SEO Risk\nChecker",
            font=("Arial", 30, "bold"),
            text_color=GOLD,
            justify="left"
        )
        title.pack(anchor="w", padx=24, pady=(28, 6))

        subtitle = ctk.CTkLabel(
            sidebar,
            text="Parametreli URL index riski,\ncanonical ve noindex kontrolü",
            font=("Arial", 14),
            text_color=MUTED,
            justify="left"
        )
        subtitle.pack(anchor="w", padx=24, pady=(0, 24))

        ctk.CTkLabel(
            sidebar,
            text="Siteler",
            font=("Arial", 15, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=24)

        self.url_box = ctk.CTkTextbox(
            sidebar,
            height=220,
            fg_color="#101010",
            border_color=GOLD_DARK,
            border_width=1,
            text_color=TEXT
        )
        self.url_box.pack(fill="x", padx=24, pady=(8, 14))
        self.url_box.insert("1.0", "https://ebubekirbastama.com.tr/\n")

        self.btn_load = ctk.CTkButton(
            sidebar,
            text="TXT Yükle",
            fg_color="#242424",
            hover_color="#333333",
            text_color=TEXT,
            command=self.load_txt
        )
        self.btn_load.pack(fill="x", padx=24, pady=5)

        self.btn_start = ctk.CTkButton(
            sidebar,
            text="Taramayı Başlat",
            fg_color=GOLD,
            hover_color=GOLD_DARK,
            text_color="#000000",
            font=("Arial", 15, "bold"),
            command=self.start_scan
        )
        self.btn_start.pack(fill="x", padx=24, pady=(18, 5))

        # İptal Et Butonu Eklendi
        self.btn_stop = ctk.CTkButton(
            sidebar,
            text="Taramayı Durdur",
            fg_color="#4A1515",
            hover_color="#631C1C",
            text_color="#FFFFFF",
            state="disabled",
            command=self.stop_scan
        )
        self.btn_stop.pack(fill="x", padx=24, pady=5)

        self.btn_export = ctk.CTkButton(
            sidebar,
            text="CSV Dışa Aktar",
            fg_color="#242424",
            hover_color="#333333",
            text_color=TEXT,
            command=self.export_csv
        )
        self.btn_export.pack(fill="x", padx=24, pady=5)

        self.btn_clear = ctk.CTkButton(
            sidebar,
            text="Temizle",
            fg_color="#2A1111",
            hover_color="#481919",
            text_color="#FFB4B4",
            command=self.clear_results
        )
        self.btn_clear.pack(fill="x", padx=24, pady=5)

        self.status_label = ctk.CTkLabel(
            sidebar,
            text="Hazır",
            font=("Arial", 13),
            text_color=MUTED
        )
        self.status_label.pack(anchor="w", padx=24, pady=(24, 4))

        self.progress = ctk.CTkProgressBar(
            sidebar,
            progress_color=GOLD,
            fg_color="#2A2A2A"
        )
        self.progress.pack(fill="x", padx=24, pady=8)
        self.progress.set(0)

        header = ctk.CTkFrame(main, fg_color=CARD, corner_radius=18)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure((0, 1, 2), weight=1)

        self.card_total = self.stat_card(header, "Toplam", "0")
        self.card_total.grid(row=0, column=0, padx=10, pady=14, sticky="ew")

        self.card_high = self.stat_card(header, "Yüksek Risk", "0")
        self.card_high.grid(row=0, column=1, padx=10, pady=14, sticky="ew")

        self.card_medium = self.stat_card(header, "Orta Risk", "0")
        self.card_medium.grid(row=0, column=2, padx=10, pady=14, sticky="ew")

        table_frame = ctk.CTkFrame(main, fg_color=CARD, corner_radius=18)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#111111",
            foreground="#F5F5F5",
            rowheight=34,
            fieldbackground="#111111",
            bordercolor="#222222",
            borderwidth=0,
            font=("Arial", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#1F1F1F",
            foreground=GOLD,
            font=("Arial", 10, "bold")
        )
        style.map(
            "Treeview",
            background=[("selected", GOLD_DARK)],
            foreground=[("selected", "#FFFFFF")]
        )

        columns = (
            "risk",
            "status",
            "url",
            "canonical_ok",
            "robots",
            "spam",
            "notes"
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings"
        )

        self.tree.heading("risk", text="Risk")
        self.tree.heading("status", text="HTTP")
        self.tree.heading("url", text="Test URL")
        self.tree.heading("canonical_ok", text="Canonical")
        self.tree.heading("robots", text="Robots")
        self.tree.heading("spam", text="Spam Kelime")
        self.tree.heading("notes", text="Not")

        self.tree.column("risk", width=90, anchor="center")
        self.tree.column("status", width=70, anchor="center")
        self.tree.column("url", width=360)
        self.tree.column("canonical_ok", width=90, anchor="center")
        self.tree.column("robots", width=130)
        self.tree.column("spam", width=120)
        self.tree.column("notes", width=360)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns", pady=14)
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ctk.CTkFrame(main, fg_color=CARD, corner_radius=18)
        log_frame.grid(row=3, column=0, sticky="ew", pady=(16, 0))

        ctk.CTkLabel(
            log_frame,
            text="İşlem Logları",
            font=("Arial", 14, "bold"),
            text_color=GOLD
        ).pack(anchor="w", padx=14, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(
            log_frame,
            height=105,
            fg_color="#101010",
            text_color=TEXT,
            border_color="#252525",
            border_width=1
        )
        self.log_box.pack(fill="x", padx=14, pady=(0, 14))

    def stat_card(self, parent, title, value):
        frame = ctk.CTkFrame(parent, fg_color="#101010", corner_radius=14)

        label = ctk.CTkLabel(
            frame,
            text=title,
            font=("Arial", 13),
            text_color=MUTED
        )
        label.pack(anchor="w", padx=18, pady=(14, 0))

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            font=("Arial", 28, "bold"),
            text_color=GOLD
        )
        value_label.pack(anchor="w", padx=18, pady=(2, 14))

        frame.value_label = value_label
        return frame

    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.update_idletasks()

    def load_txt(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt")]
        )

        if not path:
            return

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        self.url_box.delete("1.0", "end")
        self.url_box.insert("1.0", content)
        self.log(f"TXT yüklendi: {path}")

    def get_sites(self):
        raw = self.url_box.get("1.0", "end").strip().splitlines()
        sites = []

        for line in raw:
            line = line.strip()
            if line:
                sites.append(clean_url(line))

        return list(dict.fromkeys(sites))

    def start_scan(self):
        if self.running:
            messagebox.showwarning("Uyarı", "Tarama zaten çalışıyor.")
            return

        sites = self.get_sites()
        if not sites:
            messagebox.showwarning("Uyarı", "En az bir site gir.")
            return

        self.clear_results()
        self.running = True
        self.stop_requested = False
        self.btn_start.configure(state="disabled", text="Taranıyor...")
        self.btn_stop.configure(state="normal")
        
        thread = threading.Thread(target=self.scan_worker, args=(sites,), daemon=True)
        thread.start()

    def stop_scan(self):
        if self.running:
            self.stop_requested = True
            self.log("DURDURMA İSTEĞİ ALINDI. Mevcut thread'lerin bitmesi bekleniyor...")
            self.status_label.configure(text="Durduruluyor...")

    def scan_worker(self, sites):
        tasks = []
        for base_url in sites:
            for param in TEST_PARAMS:
                tasks.append((base_url, base_url + param))

        total_jobs = len(tasks)
        completed = 0

        self.log(f"Tarama başladı. Toplam iş yükü: {total_jobs} URL")
        self.status_label.configure(text="Tarama çalışıyor...")

        # max_workers=5 ayarı ile aynı anda 5 isteği paralel atar. İstediğin gibi optimize edebilirsin.
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(analyze_url, b, t): t for b, t in tasks}
            
            for future in as_completed(future_to_url):
                if self.stop_requested:
                    self.log("Tarama kullanıcı tarafından durduruldu.")
                    break
                
                try:
                    data = future.result()
                    self.results.append(data)
                    self.insert_result(data)
                except Exception as exc:
                    self.log(f"Thread hatası meydana geldi: {exc}")
                
                completed += 1
                # UI güncellemelerini ana thread güvenliğinde yapmak için:
                self.after(0, self.progress.set, completed / total_jobs)
                self.after(0, self.update_stats)

        self.running = False
        self.btn_start.configure(state="normal", text="Taramayı Başlat")
        self.btn_stop.configure(state="disabled")
        
        if self.stop_requested:
            self.status_label.configure(text="Tarama durduruldu")
        else:
            self.status_label.configure(text="Tarama tamamlandı")
            self.log("Tarama başarıyla tamamlandı.")

        if self.results:
            self.auto_save_csv()

    def insert_result(self, data):
        robots_text = data["meta_robots"] or data["x_robots_tag"] or "-"
        canonical_text = "OK" if data["canonical_ok"] else "YOK/HATALI"

        self.tree.insert(
            "",
            "end",
            values=(
                data["risk"],
                data["status"],
                data["test_url"],
                canonical_text,
                robots_text,
                data["spam_words"] or "-",
                data["notes"]
            )
        )

    def update_stats(self):
        total = len(self.results)
        high = len([r for r in self.results if r["risk"] == "HIGH"])
        medium = len([r for r in self.results if r["risk"] == "MEDIUM"])

        self.card_total.value_label.configure(text=str(total))
        self.card_high.value_label.configure(text=str(high))
        self.card_medium.value_label.configure(text=str(medium))

    def export_csv(self):
        if not self.results:
            messagebox.showwarning("Uyarı", "Dışa aktarılacak veri yok.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")]
        )

        if not path:
            return

        pd.DataFrame(self.results).to_csv(
            path,
            index=False,
            encoding="utf-8-sig"
        )

        self.log(f"CSV dışa aktarıldı: {path}")
        messagebox.showinfo("Başarılı", "CSV raporu kaydedildi.")

    def auto_save_csv(self):
        path = os.path.abspath("seo_param_risk_report.csv")
        pd.DataFrame(self.results).to_csv(
            path,
            index=False,
            encoding="utf-8-sig"
        )
        self.log(f"Otomatik rapor kaydedildi: {path}")

    def clear_results(self):
        self.results = []
        self.progress.set(0)

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.card_total.value_label.configure(text="0")
        self.card_high.value_label.configure(text="0")
        self.card_medium.value_label.configure(text="0")

        self.log_box.delete("1.0", "end")
        self.status_label.configure(text="Hazır")


if __name__ == "__main__":
    app = SeoCheckerApp()
    app.mainloop()