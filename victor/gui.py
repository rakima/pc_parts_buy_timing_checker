from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

from PIL import Image, ImageTk

from victor.database import VictorRepository
from victor.evaluator import LABELS, MESSAGES
from victor.models import EvaluationResult, Product, TimingStatus
from victor.services import InvestigationResult, PriceInvestigationService


IMAGE_FILES = {
    TimingStatus.WAITING: "victor_00_waiting.png",
    TimingStatus.RESEARCHING: "victor_01_researching.png",
    TimingStatus.BAD: "victor_02_bad.png",
    TimingStatus.INSUFFICIENT: "victor_03_neutral.png",
    TimingStatus.NEUTRAL: "victor_03_neutral.png",
    TimingStatus.GOOD: "victor_04_good.png",
    TimingStatus.BUY: "victor_05_buy.png",
    TimingStatus.BEST_BUY: "victor_06_best_buy.png",
}

COLORS = {
    "ink": "#0b0907",
    "leather": "#17110d",
    "wood": "#24170f",
    "wood_light": "#352318",
    "gold": "#b89753",
    "gold_bright": "#d8bd78",
    "brass_dark": "#6f572d",
    "paper": "#d7c59d",
    "muted": "#9e8b68",
    "selection": "#4a3420",
}

ACCENT_COLORS = {
    TimingStatus.WAITING: COLORS["gold"],
    TimingStatus.RESEARCHING: COLORS["gold_bright"],
    TimingStatus.BAD: "#8f3430",
    TimingStatus.INSUFFICIENT: "#a8782e",
    TimingStatus.NEUTRAL: "#b37a2c",
    TimingStatus.GOOD: "#77834b",
    TimingStatus.BUY: "#37694a",
    TimingStatus.BEST_BUY: "#d1a83d",
}


class VictorApp(ttk.Frame):
    def __init__(self, master: tk.Tk, repository: VictorRepository,
                 service: PriceInvestigationService, image_directory: Path,
                 logger: logging.Logger) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.repository = repository
        self.service = service
        self.image_directory = image_directory
        self.logger = logger
        self.products: list[Product] = []
        self.image_cache: dict[TimingStatus, ImageTk.PhotoImage] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._configure_theme()
        self._build_ui()
        self.refresh_products()
        self.after(100, self._process_events)

    def _configure_theme(self) -> None:
        self.master.configure(background=COLORS["ink"])
        style = ttk.Style(self.master)
        style.theme_use("clam")
        style.configure(".", background=COLORS["ink"], foreground=COLORS["paper"],
                        fieldbackground=COLORS["leather"], bordercolor=COLORS["brass_dark"],
                        lightcolor=COLORS["gold"], darkcolor=COLORS["ink"],
                        font=("Yu Gothic UI", 10))
        style.configure("TFrame", background=COLORS["ink"])
        style.configure("Wood.TFrame", background=COLORS["wood"])
        style.configure("TLabel", background=COLORS["ink"], foreground=COLORS["paper"])
        style.configure("Title.TLabel", background=COLORS["ink"], foreground=COLORS["gold_bright"],
                        font=("Yu Mincho", 22, "bold"))
        style.configure("Heading.TLabel", background=COLORS["wood"], foreground=COLORS["gold"],
                        font=("Yu Mincho", 12, "bold"))
        style.configure("Image.TLabel", background=COLORS["wood"], foreground=COLORS["gold"])
        style.configure("PanelMuted.TLabel", background=COLORS["wood"], foreground=COLORS["muted"])
        style.configure("Caption.TLabel", background=COLORS["wood"], foreground=COLORS["muted"])
        style.configure("Value.TLabel", background=COLORS["wood"], foreground=COLORS["paper"],
                        font=("Yu Gothic UI", 11, "bold"))
        style.configure("Quote.TLabel", background=COLORS["wood"], foreground=COLORS["gold_bright"],
                        font=("Yu Mincho", 12))
        style.configure("Plate.TButton", background=COLORS["brass_dark"], foreground="#f1e4c1",
                        borderwidth=1, relief="raised", padding=(12, 7), font=("Yu Gothic UI", 10, "bold"))
        style.map("Plate.TButton",
                  background=[("pressed", "#4e3b20"), ("active", "#8b6d37"), ("disabled", "#302a22")],
                  foreground=[("disabled", "#766c5c")])
        style.configure("TEntry", fieldbackground="#100d0a", foreground=COLORS["paper"],
                        insertcolor=COLORS["gold_bright"], bordercolor=COLORS["brass_dark"], padding=6)
        style.configure("TCheckbutton", background=COLORS["ink"], foreground=COLORS["paper"])
        style.map("TCheckbutton", background=[("active", COLORS["ink"])])
        style.configure("Ledger.Treeview", background="#17120d", fieldbackground="#17120d",
                        foreground=COLORS["paper"], rowheight=30, bordercolor=COLORS["brass_dark"])
        style.configure("Ledger.Treeview.Heading", background=COLORS["wood_light"],
                        foreground=COLORS["gold_bright"], font=("Yu Mincho", 10, "bold"), relief="flat")
        style.map("Ledger.Treeview", background=[("selected", COLORS["selection"])],
                  foreground=[("selected", "#f4e6c2")])
        for status, color in ACCENT_COLORS.items():
            style.configure(f"{status.value}.Status.TLabel", background=COLORS["wood"],
                            foreground=color, font=("Yu Mincho", 15, "bold"))
            style.configure(f"{status.value}.Quote.TLabel", background=COLORS["wood"],
                            foreground=color, font=("Yu Mincho", 12))

    def _build_ui(self) -> None:
        self.master.title("時期判定官 ヴィクトル")
        self.master.geometry("1220x780")
        self.master.minsize(1080, 680)
        self.pack(fill=tk.BOTH, expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        title = ttk.Label(self, text="時期判定官 ヴィクトル", style="Title.TLabel")
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        left_border = tk.Frame(self, background=COLORS["wood"], highlightbackground=COLORS["gold"],
                               highlightthickness=1, bd=0)
        left_border.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        left = ttk.Frame(left_border, style="Wood.TFrame", padding=10)
        left.pack(fill=tk.BOTH, expand=True)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="監視商品目録", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        self.product_list = tk.Listbox(left, width=30, exportselection=False, bd=0,
                                      background="#14100c", foreground=COLORS["paper"],
                                      selectbackground=COLORS["selection"], selectforeground="#f4e6c2",
                                      highlightbackground=COLORS["brass_dark"], highlightthickness=1,
                                      font=("Yu Mincho", 10), activestyle="none")
        self.product_list.grid(row=1, column=0, sticky="nsew", pady=6)
        self.product_list.bind("<<ListboxSelect>>", self._on_product_selected)

        buttons = ttk.Frame(left, style="Wood.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="商品登録", style="Plate.TButton", command=self.add_product).pack(side=tk.LEFT)
        ttk.Button(buttons, text="編集", style="Plate.TButton", command=self.edit_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="削除", style="Plate.TButton", command=self.delete_product).pack(side=tk.LEFT)

        right = tk.Frame(self, background=COLORS["wood"], highlightbackground=COLORS["gold"],
                         highlightthickness=1, bd=0, padx=16, pady=14)
        self.result_panel = right
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        self.detail_title = ttk.Label(right, text="商品を選択してください", style="Heading.TLabel")
        self.detail_title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        content = ttk.Frame(right, style="Wood.TFrame")
        content.grid(row=1, column=0, sticky="nw", pady=(4, 0))
        self.image_label = ttk.Label(content, anchor="center", style="Image.TLabel")
        self.image_label.grid(row=0, column=0, rowspan=7, sticky="nw", padx=(0, 24))
        self.values: dict[str, ttk.Label] = {}
        for row, (key, caption) in enumerate((
            ("status", "判定"), ("current", "現在価格"), ("average", "30日平均"),
            ("difference", "平均との差"), ("lowest", "30日最安値"), ("fetched", "取得日時"),
        )):
            ttk.Label(content, text=caption, style="Caption.TLabel").grid(row=row, column=1, sticky="w", pady=4)
            label = ttk.Label(content, text="-", style="Value.TLabel")
            label.grid(row=row, column=2, sticky="w", padx=(15, 0), pady=4)
            self.values[key] = label

        self.message_label = ttk.Label(right, text="商品を選び、価格を調査してください。",
                                       wraplength=760, style="Quote.TLabel")
        self.message_label.grid(row=2, column=0, sticky="ew", pady=(16, 8))
        self.progress_label = ttk.Label(right, text="", style="PanelMuted.TLabel")
        self.progress_label.grid(row=3, column=0, sticky="w")
        actions = ttk.Frame(right, style="Wood.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.investigate_button = ttk.Button(actions, text="価格を調査する", style="Plate.TButton", command=self.investigate)
        self.investigate_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="価格履歴", style="Plate.TButton", command=self.show_history).pack(side=tk.LEFT, padx=6)
        self._show_status(TimingStatus.WAITING)

    def refresh_products(self, selected_id: int | None = None) -> None:
        self.products = self.repository.list_products()
        self.product_list.delete(0, tk.END)
        selected_index = None
        for index, product in enumerate(self.products):
            prefix = "" if product.enabled else "[無効] "
            self.product_list.insert(tk.END, f"{prefix}{product.name}")
            if product.id == selected_id:
                selected_index = index
        if selected_index is not None:
            self.product_list.selection_set(selected_index)
            self.product_list.event_generate("<<ListboxSelect>>")

    def selected_product(self) -> Product | None:
        selection = self.product_list.curselection()
        return self.products[selection[0]] if selection else None

    def _on_product_selected(self, _event: object = None) -> None:
        product = self.selected_product()
        if product is None:
            return
        self.detail_title.configure(text=product.name)
        history = self.repository.get_price_history(product.id or 0, 1)
        if history:
            latest = history[0]
            self.values["current"].configure(text=f"{latest.price:,}円")
            self.values["fetched"].configure(text=latest.fetched_at.strftime("%Y-%m-%d %H:%M"))
        else:
            self.values["current"].configure(text="未取得")
            self.values["fetched"].configure(text="-")
        for key in ("status", "average", "difference", "lowest"):
            self.values[key].configure(text="-")
        self.progress_label.configure(text=f"{product.category} / {product.site}")

    def add_product(self) -> None:
        ProductDialog(self.master, "商品登録", None, self._save_product)

    def edit_product(self) -> None:
        product = self.selected_product()
        if product is None:
            messagebox.showinfo("編集", "商品を選択してください。", parent=self.master)
            return
        ProductDialog(self.master, "商品編集", product, self._save_product)

    def _save_product(self, product: Product) -> None:
        action = "商品登録" if product.id is None else "商品更新"
        saved = self.repository.save_product(product)
        self.logger.info("%s product=%s url=%s", action, saved.name, saved.url)
        self.refresh_products(saved.id)

    def delete_product(self) -> None:
        product = self.selected_product()
        if product is None or product.id is None:
            messagebox.showinfo("削除", "商品を選択してください。", parent=self.master)
            return
        if not messagebox.askyesno("商品削除", f"「{product.name}」と価格履歴を削除しますか？", parent=self.master):
            return
        self.repository.delete_product(product.id)
        self.logger.info("商品削除 product=%s url=%s", product.name, product.url)
        self.refresh_products()
        self.detail_title.configure(text="商品を選択してください")

    def investigate(self) -> None:
        product = self.selected_product()
        if product is None:
            messagebox.showinfo("価格調査", "商品を選択してください。", parent=self.master)
            return
        if not product.enabled:
            messagebox.showwarning("価格調査", "無効な商品は調査できません。", parent=self.master)
            return
        self.investigate_button.state(["disabled"])
        self._show_status(TimingStatus.RESEARCHING)
        self.progress_label.configure(text="ヴィクトルが価格を調査中……")
        threading.Thread(target=self._investigate_worker, args=(product,), daemon=True).start()

    def _investigate_worker(self, product: Product) -> None:
        try:
            result = self.service.investigate(
                product, lambda message: self.events.put(("progress", message))
            )
            self.events.put(("success", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self.progress_label.configure(text=str(payload))
                elif event == "success":
                    self._show_result(payload)  # type: ignore[arg-type]
                    self.investigate_button.state(["!disabled"])
                elif event == "error":
                    self.progress_label.configure(text="価格取得に失敗しました")
                    self.investigate_button.state(["!disabled"])
                    messagebox.showerror("価格取得エラー", str(payload), parent=self.master)
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _show_result(self, result: InvestigationResult) -> None:
        evaluation = result.evaluation
        self._show_status(evaluation.status, evaluation)
        self.values["fetched"].configure(text=result.fetched_at.strftime("%Y-%m-%d %H:%M"))
        self.progress_label.configure(text="調査が完了しました")

    def _show_status(self, status: TimingStatus, result: EvaluationResult | None = None) -> None:
        accent = ACCENT_COLORS[status]
        self.result_panel.configure(highlightbackground=accent)
        self.values["status"].configure(text=LABELS[status], style=f"{status.value}.Status.TLabel")
        self.message_label.configure(text=MESSAGES[status], style=f"{status.value}.Quote.TLabel")
        if result:
            self.values["current"].configure(text=f"{result.current_price:,}円")
            self.values["average"].configure(text=self._yen(result.average_price))
            difference = "-" if result.difference_percent is None else f"{result.difference_percent:+.1f}%"
            self.values["difference"].configure(text=difference)
            self.values["lowest"].configure(text=self._yen(result.lowest_price))
        image = self._load_image(status)
        self.image_label.configure(image=image, text="" if image else f"ヴィクトル\n{LABELS[status]}")
        self.image_label.image = image

    def _load_image(self, status: TimingStatus) -> ImageTk.PhotoImage | None:
        if status in self.image_cache:
            return self.image_cache[status]
        path = self.image_directory / IMAGE_FILES[status]
        if not path.exists():
            return None
        try:
            with Image.open(path) as original:
                rendered = original.convert("RGB")
                rendered.thumbnail((520, 440), Image.Resampling.LANCZOS)
                image = ImageTk.PhotoImage(rendered, master=self.master)
            self.image_cache[status] = image
            return image
        except (OSError, tk.TclError):
            self.logger.exception("画像読み込み失敗 path=%s", path)
            return None

    def show_history(self) -> None:
        product = self.selected_product()
        if product is None or product.id is None:
            messagebox.showinfo("価格履歴", "商品を選択してください。", parent=self.master)
            return
        window = tk.Toplevel(self.master)
        window.title(f"価格履歴 - {product.name}")
        window.geometry("520x420")
        window.configure(background=COLORS["ink"])
        ttk.Label(window, text=f"相場帳　{product.name}", style="Title.TLabel").pack(anchor="w", padx=12, pady=(12, 0))
        tree = ttk.Treeview(window, columns=("fetched", "price"), show="headings", style="Ledger.Treeview")
        tree.heading("fetched", text="日時")
        tree.heading("price", text="価格")
        tree.column("fetched", width=260)
        tree.column("price", width=180, anchor=tk.E)
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        for record in self.repository.get_price_history(product.id):
            tree.insert("", tk.END, values=(record.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                                            f"{record.price:,}円"))

    @staticmethod
    def _yen(value: float | int | None) -> str:
        return "-" if value is None else f"{value:,.0f}円"


class ProductDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, product: Product | None,
                 on_save: object) -> None:
        super().__init__(parent)
        self.product = product
        self.on_save = on_save
        self.title(title)
        self.configure(background=COLORS["ink"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.variables = {
            "name": tk.StringVar(value=product.name if product else ""),
            "category": tk.StringVar(value=product.category if product else ""),
            "url": tk.StringVar(value=product.url if product else ""),
            "site": tk.StringVar(value=product.site if product else "汎用ECサイト"),
            "enabled": tk.BooleanVar(value=product.enabled if product else True),
        }
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        for row, (key, caption) in enumerate((
            ("name", "商品名"), ("category", "カテゴリ"), ("url", "商品URL"), ("site", "取得サイト")
        )):
            ttk.Label(frame, text=caption).grid(row=row, column=0, sticky="w", pady=5)
            if key == "site":
                field = ttk.Combobox(
                    frame, textvariable=self.variables[key], width=49,
                    values=("汎用ECサイト", "ツクモ"), state="readonly",
                )
            else:
                field = ttk.Entry(frame, textvariable=self.variables[key], width=52)
            field.grid(row=row, column=1, pady=5)
        ttk.Checkbutton(frame, text="有効", variable=self.variables["enabled"]).grid(row=4, column=1, sticky="w", pady=5)
        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="キャンセル", style="Plate.TButton", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(actions, text="保存", style="Plate.TButton", command=self._submit).pack(side=tk.LEFT, padx=(6, 0))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._submit())

    def _submit(self) -> None:
        values = {key: variable.get() for key, variable in self.variables.items()}
        if not values["name"] or not values["category"] or not values["url"] or not values["site"]:
            messagebox.showwarning("入力確認", "すべての項目を入力してください。", parent=self)
            return
        parsed = urlparse(str(values["url"]))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            messagebox.showwarning("入力確認", "有効な http(s) URLを入力してください。", parent=self)
            return
        product = self.product or Product("", "", "")
        product.name = str(values["name"]).strip()
        product.category = str(values["category"]).strip()
        product.url = str(values["url"]).strip()
        product.site = str(values["site"]).strip()
        product.enabled = bool(values["enabled"])
        self.on_save(product)  # type: ignore[operator]
        self.destroy()
