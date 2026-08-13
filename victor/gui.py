from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from victor.catalogs import CatalogFetcherRegistry
from victor.database import VictorRepository
from victor.evaluator import LABELS, MESSAGES
from victor.models import EvaluationResult, Product, ProductCandidate, TimingStatus
from victor.normalization import matches_product_name
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

MINIMUM_RESEARCH_SECONDS = 3.0
STATUS_IMAGE_SIZE = (440, 440)


def wait_for_minimum_duration(
    started_at: float,
    minimum_seconds: float = MINIMUM_RESEARCH_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    remaining = minimum_seconds - (clock() - started_at)
    if remaining > 0:
        sleeper(remaining)


class VictorApp(ttk.Frame):
    def __init__(self, master: tk.Tk, repository: VictorRepository,
                 service: PriceInvestigationService, catalogs: CatalogFetcherRegistry,
                 image_directory: Path,
                 logger: logging.Logger) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.repository = repository
        self.service = service
        self.catalogs = catalogs
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
        ttk.Button(buttons, text="商品を探す", style="Plate.TButton", command=self.add_product).pack(side=tk.LEFT)
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
        self.image_frame = tk.Frame(
            content, width=STATUS_IMAGE_SIZE[0], height=STATUS_IMAGE_SIZE[1],
            background=COLORS["wood"], bd=0,
        )
        self.image_frame.grid(row=0, column=0, rowspan=7, sticky="nw", padx=(0, 24))
        self.image_frame.grid_propagate(False)
        self.image_label = ttk.Label(self.image_frame, anchor="center", style="Image.TLabel")
        self.image_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
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
        for key in ("average", "difference", "lowest"):
            self.values[key].configure(text="-")
        history = self.repository.get_price_history(product.id or 0, 1)
        if history:
            latest = history[0]
            self.values["status"].configure(text="-", style="Value.TLabel")
            self.values["current"].configure(text=f"{latest.price:,}円")
            self.values["fetched"].configure(text=latest.fetched_at.strftime("%Y-%m-%d %H:%M"))
        else:
            self.values["current"].configure(text="未取得")
            self.values["fetched"].configure(text="-")
            self._show_status(TimingStatus.WAITING)
        self.progress_label.configure(text=f"{product.category} / {product.site}")

    def add_product(self) -> None:
        ProductSearchDialog(
            self.master, self.catalogs, self.logger, self._add_candidate
        )

    def edit_product(self) -> None:
        product = self.selected_product()
        if product is None:
            messagebox.showinfo("編集", "商品を選択してください。", parent=self.master)
            return
        ProductDialog(self.master, "商品編集", product, self._save_product)

    def _add_candidate(self, candidate: ProductCandidate) -> bool:
        existing = self.repository.get_product_by_url(candidate.url)
        if existing:
            self.logger.info("重複登録 product=%s url=%s", candidate.name, candidate.url)
            messagebox.showinfo(
                "登録済み", f"「{existing.name}」はすでに監視対象です。", parent=self.master
            )
            self.refresh_products(existing.id)
            return False
        product = Product(
            name=candidate.name,
            category=candidate.category,
            url=candidate.url,
            site=candidate.shop,
        )
        saved = self.repository.save_product(product)
        self.logger.info("監視対象追加 product=%s shop=%s category=%s url=%s",
                         saved.name, saved.site, saved.category, saved.url)
        self.refresh_products(saved.id)
        self.progress_label.configure(text=f"「{saved.name}」を監視対象に加えました。")
        return True

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
        started_at = time.monotonic()
        try:
            result = self.service.investigate(
                product, lambda message: self.events.put(("progress", message))
            )
            outcome: tuple[str, object] = ("success", result)
        except Exception as exc:
            outcome = ("error", str(exc))
        self.events.put(("progress", "ヴィクトルが判定を吟味中……"))
        wait_for_minimum_duration(started_at)
        self.events.put(outcome)

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
                rendered.thumbnail(STATUS_IMAGE_SIZE, Image.Resampling.LANCZOS)
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


class ProductSearchDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, catalogs: CatalogFetcherRegistry,
                 logger: logging.Logger,
                 on_add: Callable[[ProductCandidate], bool]) -> None:
        super().__init__(parent)
        self.catalogs = catalogs
        self.logger = logger
        self.on_add = on_add
        self.candidates: list[ProductCandidate] = []
        self.visible_candidates: list[ProductCandidate] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.title("商品検索 - ツクモ商品目録")
        self.geometry("900x620")
        self.minsize(760, 520)
        self.configure(background=COLORS["ink"])
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        self.shop = tk.StringVar(value=self.catalogs.shops[0] if self.catalogs.shops else "")
        self.category = tk.StringVar()
        self.query = tk.StringVar()

        ttk.Label(frame, text="商品目録から監視対象を選ぶ", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )
        ttk.Label(frame, text="店舗").grid(row=1, column=0, sticky="w", pady=4)
        self.shop_field = ttk.Combobox(
            frame, textvariable=self.shop, values=self.catalogs.shops, state="readonly", width=20
        )
        self.shop_field.grid(row=1, column=1, sticky="w", pady=4)
        self.shop_field.bind("<<ComboboxSelected>>", self._update_categories)
        ttk.Label(frame, text="カテゴリ").grid(row=2, column=0, sticky="w", pady=4)
        self.category_field = ttk.Combobox(
            frame, textvariable=self.category, state="readonly", width=20
        )
        self.category_field.grid(row=2, column=1, sticky="w", pady=4)
        self.fetch_button = ttk.Button(
            frame, text="商品一覧を取得", style="Plate.TButton", command=self.fetch_catalog
        )
        self.fetch_button.grid(row=1, column=2, rowspan=2, sticky="e", padx=(10, 0))

        search = ttk.Frame(frame)
        search.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="検索").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(search, textvariable=self.query).grid(row=0, column=1, sticky="ew")
        self.query.trace_add("write", lambda *_args: self._filter_candidates())

        columns = ("name", "price", "manufacturer", "stock")
        self.results = ttk.Treeview(
            frame, columns=columns, show="headings", style="Ledger.Treeview", selectmode="browse"
        )
        self.results.heading("name", text="商品名")
        self.results.heading("price", text="現在価格")
        self.results.heading("manufacturer", text="メーカー")
        self.results.heading("stock", text="在庫・出荷")
        self.results.column("name", width=390)
        self.results.column("price", width=100, anchor=tk.E)
        self.results.column("manufacturer", width=150)
        self.results.column("stock", width=150)
        self.results.grid(row=4, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.results.yview)
        scrollbar.grid(row=4, column=3, sticky="ns")
        self.results.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.status = ttk.Label(footer, text="店舗とカテゴリを選び、商品一覧を取得してください。")
        self.status.grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="閉じる", style="Plate.TButton", command=self.destroy).grid(
            row=0, column=1, padx=6
        )
        self.add_button = ttk.Button(
            footer, text="監視対象に追加", style="Plate.TButton", command=self.add_selected
        )
        self.add_button.grid(row=0, column=2)
        self._update_categories()
        self.after(100, self._process_events)

    def _update_categories(self, _event: object = None) -> None:
        try:
            categories = self.catalogs.get(self.shop.get()).supported_categories
        except Exception:
            categories = ()
        self.category_field.configure(values=categories)
        self.category.set(categories[0] if categories else "")

    def fetch_catalog(self) -> None:
        shop = self.shop.get()
        category = self.category.get()
        if not shop or not category:
            messagebox.showwarning("商品一覧", "店舗とカテゴリを選択してください。", parent=self)
            return
        self.fetch_button.state(["disabled"])
        self.add_button.state(["disabled"])
        self.status.configure(text="ヴィクトルが商品を調査中……")
        self.logger.info("商品一覧取得開始 shop=%s category=%s", shop, category)
        threading.Thread(
            target=self._fetch_worker, args=(shop, category), daemon=True
        ).start()

    def _fetch_worker(self, shop: str, category: str) -> None:
        try:
            candidates = self.catalogs.get(shop).fetch(category)
            self.events.put(("success", candidates))
        except Exception as exc:
            self.logger.exception("一覧取得失敗 shop=%s category=%s", shop, category)
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                event, payload = self.events.get_nowait()
                self.fetch_button.state(["!disabled"])
                self.add_button.state(["!disabled"])
                if event == "success":
                    self.candidates = list(payload)  # type: ignore[arg-type]
                    self.logger.info("商品一覧取得成功 shop=%s category=%s count=%s",
                                     self.shop.get(), self.category.get(), len(self.candidates))
                    self._filter_candidates()
                    if self.candidates:
                        self.status.configure(text=f"{len(self.candidates)}件を取得しました。")
                    else:
                        self.status.configure(text="商品が見つかりませんでした。")
                        messagebox.showinfo("商品一覧", "商品が見つかりませんでした。", parent=self)
                else:
                    self.status.configure(text="商品一覧の取得に失敗しました。")
                    messagebox.showerror("商品一覧取得エラー", str(payload), parent=self)
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _filter_candidates(self) -> None:
        query = self.query.get()
        self.visible_candidates = [
            candidate for candidate in self.candidates
            if matches_product_name(candidate.name, query)
        ]
        self.results.delete(*self.results.get_children())
        for index, candidate in enumerate(self.visible_candidates):
            self.results.insert("", tk.END, iid=str(index), values=(
                candidate.name,
                f"{candidate.price:,}円",
                candidate.manufacturer or "-",
                candidate.stock_status or "-",
            ))
        if query:
            self.status.configure(
                text=f"{len(self.visible_candidates)}件 / 取得{len(self.candidates)}件"
            )

    def add_selected(self) -> None:
        selection = self.results.selection()
        if not selection:
            messagebox.showinfo("監視対象", "商品を選択してください。", parent=self)
            return
        candidate = self.visible_candidates[int(selection[0])]
        if self.on_add(candidate):
            self.destroy()


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
            ("name", "商品名"), ("category", "カテゴリ")
        )):
            ttk.Label(frame, text=caption).grid(row=row, column=0, sticky="w", pady=5)
            field = ttk.Entry(frame, textvariable=self.variables[key], width=52)
            field.grid(row=row, column=1, pady=5)
        ttk.Label(frame, text="取得元").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Label(frame, text=self.variables["site"].get()).grid(row=2, column=1, sticky="w", pady=5)
        ttk.Checkbutton(frame, text="有効", variable=self.variables["enabled"]).grid(row=3, column=1, sticky="w", pady=5)
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="キャンセル", style="Plate.TButton", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(actions, text="保存", style="Plate.TButton", command=self._submit).pack(side=tk.LEFT, padx=(6, 0))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._submit())

    def _submit(self) -> None:
        values = {key: variable.get() for key, variable in self.variables.items()}
        if not values["name"] or not values["category"]:
            messagebox.showwarning("入力確認", "すべての項目を入力してください。", parent=self)
            return
        product = self.product or Product("", "", "")
        product.name = str(values["name"]).strip()
        product.category = str(values["category"]).strip()
        product.url = str(values["url"]).strip()
        product.site = str(values["site"]).strip()
        product.enabled = bool(values["enabled"])
        self.on_save(product)  # type: ignore[operator]
        self.destroy()
