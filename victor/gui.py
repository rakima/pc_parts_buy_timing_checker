from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

from victor.database import VictorRepository
from victor.evaluator import LABELS, MESSAGES
from victor.models import EvaluationResult, Product, TimingStatus
from victor.services import InvestigationResult, PriceInvestigationService


IMAGE_FILES = {
    TimingStatus.RESEARCHING: "victor_01_researching.png",
    TimingStatus.BAD: "victor_02_bad.png",
    TimingStatus.INSUFFICIENT: "victor_03_neutral.png",
    TimingStatus.NEUTRAL: "victor_03_neutral.png",
    TimingStatus.GOOD: "victor_04_good.png",
    TimingStatus.BUY: "victor_05_buy.png",
    TimingStatus.BEST_BUY: "victor_06_best_buy.png",
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
        self.image_cache: dict[TimingStatus, tk.PhotoImage] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build_ui()
        self.refresh_products()
        self.after(100, self._process_events)

    def _build_ui(self) -> None:
        self.master.title("時期判定官 ヴィクトル")
        self.master.geometry("1000x680")
        self.master.minsize(820, 580)
        self.pack(fill=tk.BOTH, expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        title = ttk.Label(self, text="時期判定官 ヴィクトル", font=("Yu Gothic UI", 20, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="監視商品", font=("Yu Gothic UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.product_list = tk.Listbox(left, width=30, exportselection=False)
        self.product_list.grid(row=1, column=0, sticky="nsew", pady=6)
        self.product_list.bind("<<ListboxSelect>>", self._on_product_selected)

        buttons = ttk.Frame(left)
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="商品登録", command=self.add_product).pack(side=tk.LEFT)
        ttk.Button(buttons, text="編集", command=self.edit_product).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="削除", command=self.delete_product).pack(side=tk.LEFT)

        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.detail_title = ttk.Label(right, text="商品を選択してください", font=("Yu Gothic UI", 15, "bold"))
        self.detail_title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        content = ttk.Frame(right)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        self.image_label = ttk.Label(content, anchor="center")
        self.image_label.grid(row=0, column=0, rowspan=7, sticky="n", padx=(0, 18))
        self.values: dict[str, ttk.Label] = {}
        for row, (key, caption) in enumerate((
            ("status", "判定"), ("current", "現在価格"), ("average", "30日平均"),
            ("difference", "平均との差"), ("lowest", "30日最安値"), ("fetched", "取得日時"),
        )):
            ttk.Label(content, text=caption).grid(row=row, column=1, sticky="w", pady=4)
            label = ttk.Label(content, text="-", font=("Yu Gothic UI", 11, "bold"))
            label.grid(row=row, column=2, sticky="w", padx=(15, 0), pady=4)
            self.values[key] = label

        self.message_label = ttk.Label(right, text="商品を選び、価格を調査してください。",
                                       wraplength=600, font=("Yu Gothic UI", 12))
        self.message_label.grid(row=2, column=0, sticky="ew", pady=10)
        self.progress_label = ttk.Label(right, text="")
        self.progress_label.grid(row=3, column=0, sticky="w")
        actions = ttk.Frame(right)
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.investigate_button = ttk.Button(actions, text="価格を調査する", command=self.investigate)
        self.investigate_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="履歴表示", command=self.show_history).pack(side=tk.LEFT, padx=6)
        self._show_status(TimingStatus.NEUTRAL)

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
        self.values["status"].configure(text=LABELS[status])
        self.message_label.configure(text=MESSAGES[status])
        if result:
            self.values["current"].configure(text=f"{result.current_price:,}円")
            self.values["average"].configure(text=self._yen(result.average_price))
            difference = "-" if result.difference_percent is None else f"{result.difference_percent:+.1f}%"
            self.values["difference"].configure(text=difference)
            self.values["lowest"].configure(text=self._yen(result.lowest_price))
        image = self._load_image(status)
        self.image_label.configure(image=image, text="" if image else f"ヴィクトル\n{LABELS[status]}")
        self.image_label.image = image

    def _load_image(self, status: TimingStatus) -> tk.PhotoImage | None:
        if status in self.image_cache:
            return self.image_cache[status]
        path = self.image_directory / IMAGE_FILES[status]
        if not path.exists():
            return None
        try:
            original = tk.PhotoImage(file=path)
            divisor = max(1, max(original.width(), original.height()) // 260)
            image = original.subsample(divisor, divisor)
            self.image_cache[status] = image
            return image
        except tk.TclError:
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
        tree = ttk.Treeview(window, columns=("fetched", "price"), show="headings")
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
            ttk.Entry(frame, textvariable=self.variables[key], width=52).grid(row=row, column=1, pady=5)
        ttk.Checkbutton(frame, text="有効", variable=self.variables["enabled"]).grid(row=4, column=1, sticky="w", pady=5)
        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="キャンセル", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(actions, text="保存", command=self._submit).pack(side=tk.LEFT, padx=(6, 0))
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

