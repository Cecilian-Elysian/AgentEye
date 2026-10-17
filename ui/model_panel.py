"""Model 详情弹窗:展示 provider 的模型列表 + 搜索 + 分组 + 试调。"""

import queue
import threading
import time
import tkinter as tk

from ui.scrollbar_style import make_dark_scrollbar
from ui.theme import PALETTE, Layout, Typography, to_tk_color, to_tk_color_blended
from ui.fonts import pick_ui_family
from ui.paint import (FlatButton, FocusEntry, hairline, bind_hover_bg,
                      bind_press_bg, bind_wheel_tree, tag_subtree, wheel_tag)

from ui.mac_toplevel import MacToplevel


class ModelPanel(MacToplevel):
    FONT = pick_ui_family()

    GROUP_RULES = [
        ("Claude", ("claude",)),
        ("GPT", ("gpt-", "o1", "o3", "o4")),
        ("Gemini", ("gemini",)),
        ("Llama", ("llama",)),
        ("Qwen", ("qwen",)),
        ("DeepSeek", ("deepseek-",)),
        ("GLM", ("glm-",)),
        ("Embedding", ("embedding", "embed")),
        ("Image", ("dall-e", "image", "sdxl", "stable-diffusion")),
        ("Audio", ("whisper", "tts", "audio")),
    ]

    def __init__(self, parent, provider_name, models, on_probe=None,
                 on_reorder=None, on_after_reorder=None):
        super().__init__(
            parent, title=f"{provider_name} · 模型列表",
            on_close=self._on_close,
            show_minimize=True,
            width=440, height=540,
            resizable=True,
        )
        self.transient(parent)

        self.models = list(models or [])
        self.filtered = list(self.models)
        self.on_probe = on_probe
        self.on_reorder = on_reorder
        self.on_after_reorder = on_after_reorder
        self._drag = None
        self._probing = set()
        self.probe_btns = {}
        self._probe_results = queue.Queue()
        self._pump_scheduled = False
        self._unbind_wheel = None

        BG = to_tk_color(PALETTE.BG)
        FG = to_tk_color(PALETTE.TEXT)
        DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
        OK = to_tk_color(PALETTE.OK)

        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", padx=Layout.PAD_X,
                 pady=(Layout.PAD, Layout.ROW_GAP))
        self.count_var = tk.StringVar(value=f"{len(self.models)} 个模型")
        tk.Label(top, textvariable=self.count_var,
                 bg=BG, fg=DIM,
                 font=(self.FONT, Typography.DETAIL_SIZE)).pack(side="left")

        search_frame = tk.Frame(self.body, bg=BG)
        search_frame.pack(fill="x", padx=Layout.PAD_X)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._apply_filter())
        self.search_entry = FocusEntry(
            search_frame, textvariable=self.search_var,
            font=(self.FONT, Typography.BODY_SIZE))
        self.search_entry.pack(fill="x")

        calc_frame = tk.Frame(self.body, bg=BG)
        calc_frame.pack(fill="x", padx=Layout.PAD_X, pady=(Layout.ROW_GAP, 0))
        tk.Label(calc_frame, text="估算调用", bg=BG, fg=DIM,
                 font=(self.FONT, Typography.DETAIL_SIZE)).pack(side="left")
        self.calc_n_var = tk.StringVar(value="100")
        self.calc_n_var.trace_add("write", lambda *a: self._on_calc_change())
        FocusEntry(calc_frame, textvariable=self.calc_n_var, width=6,
                   font=(self.FONT, Typography.DETAIL_SIZE)).pack(
            side="left", padx=(4, 2))
        tk.Label(calc_frame, text="次 (按选定模型)", bg=BG, fg=DIM,
                 font=(self.FONT, Typography.DETAIL_SIZE)).pack(side="left")
        self.calc_cost_var = tk.StringVar(value="选择模型后查看")
        tk.Label(calc_frame, textvariable=self.calc_cost_var,
                 bg=BG, fg=OK,
                 font=(self.FONT, Typography.BODY_SIZE,
                       Typography.TITLE_WEIGHT)).pack(side="right")

        list_frame = tk.Frame(self.body, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=Layout.PAD_X,
                        pady=Layout.PAD_Y)

        self.canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
        self.scroll = make_dark_scrollbar(list_frame, orient="vertical",
                                          command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self._list_window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._unbind_wheel = bind_wheel_tree(self.inner, self._on_wheel)

        btn_frame = tk.Frame(self.body, bg=BG)
        btn_frame.pack(side="bottom", fill="x", padx=Layout.PAD_X,
                       pady=Layout.PAD_Y)
        FlatButton(btn_frame, text="关闭", variant="ghost", width=10,
                   on_click=self._on_close,
                   font=(self.FONT, Typography.BODY_SIZE)).pack(side="right")

        self.bind("<Escape>", lambda e: self._on_close())
        # grab 不能在构造里立即调:窗口尚未 map 时抛
        # "grab failed: window not viewable"。挂到 <Map>,映射后自动拿到
        self.bind("<Map>", self._grab_when_viewable, add="+")
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._render()

    def refresh_palette(self):
        """主题切换:逐控件自刷新。

        旧实现 walk 子树读当前色值猜语义(靠 `_LEGACY_FIELD_BG` 当哨兵),
        主题一换哨兵就失效。现在每个控件自己报新配色,加控件时这里不用改。
        """
        bg = to_tk_color(PALETTE.BG)
        try:
            self.body.configure(bg=bg)
            for w in self.body.winfo_children():
                self._walk_refresh(w, bg)
            self.canvas.configure(bg=bg)
            self.inner.configure(bg=bg)
            # 列表行由 _render 重建,这里主动重排一次让它用上新配色
            self._render()
        except tk.TclError:
            pass

    def _walk_refresh(self, w, bg):
        refresh = getattr(w, "refresh_palette", None)
        if callable(refresh):
            try:
                refresh()
            except tk.TclError:
                pass
        else:
            try:
                if w.winfo_class() in ("Frame", "Toplevel", "Label"):
                    w.configure(bg=bg)
            except tk.TclError:
                pass
        for c in w.winfo_children():
            self._walk_refresh(c, bg)

    def _apply_filter(self):
        q = self.search_var.get().lower().strip()
        if not q:
            self.filtered = list(self.models)
        else:
            self.filtered = [m for m in self.models if q in m.lower()]
        if hasattr(self, "count_var"):
            self.count_var.set(
                f"{len(self.filtered)} / {len(self.models)} 个模型")
        self._render()

    def _group(self, model_id):
        mid = model_id.lower()
        for group, keywords in self.GROUP_RULES:
            if any(k in mid for k in keywords):
                return group
        return "其他"

    def _render(self):
        try:
            scroll_pos = self.canvas.yview()[0]
        except (tk.TclError, AttributeError, IndexError):
            scroll_pos = 0.0

        for w in self.inner.winfo_children():
            w.destroy()

        BG = to_tk_color(PALETTE.BG)
        DIM = to_tk_color_blended(PALETTE.TEXT_DIM)
        FG = to_tk_color(PALETTE.TEXT)

        if not self.filtered:
            box = tk.Frame(self.inner, bg=BG)
            box.pack(fill="x", pady=Layout.PAD * 2)
            tk.Label(box, text="没有匹配的模型", bg=BG, fg=FG,
                     font=(self.FONT, Typography.BODY_SIZE)).pack(pady=(0, 4))
            tk.Label(box, text="换个关键词,或清空搜索框看全部",
                     bg=BG, fg=DIM,
                     font=(self.FONT, Typography.DETAIL_SIZE)).pack()
            try:
                self.canvas.update_idletasks()
                self.canvas.yview_moveto(0.0)
            except tk.TclError:
                pass
            return

        grouped = {}
        for m in self.filtered:
            grouped.setdefault(self._group(m), []).append(m)

        self.probe_result_vars = {}

        for group_name in ["Claude", "GPT", "Gemini", "Llama", "Qwen",
                           "DeepSeek", "GLM", "Embedding", "Image", "Audio", "其他"]:
            if group_name not in grouped:
                continue
            tk.Label(self.inner, text=group_name, bg=BG, fg=DIM,
                     font=(self.FONT, Typography.DETAIL_SIZE,
                           Typography.TITLE_WEIGHT)).pack(
                anchor="w", pady=(Layout.PAD_Y, 2))
            for m in grouped[group_name]:
                # 行不铺色块:模型动辄几十条,每条一块灰砖就是一片噪点。
                # 分组靠组标题的字重,行与行之间靠 hairline。
                row = tk.Frame(self.inner, bg=BG, cursor="hand2")
                row.pack(fill="x")
                row._model_id = m
                name_lbl = tk.Label(row, text=m, bg=BG, fg=FG,
                                    font=(self.FONT, Typography.DETAIL_SIZE),
                                    anchor="w")
                name_lbl.pack(side="left", padx=8, pady=3)
                chain = [row, name_lbl]
                if self.on_probe:
                    probe_var = tk.StringVar(value="")
                    self.probe_result_vars[m] = probe_var
                    result_lbl = tk.Label(row, textvariable=probe_var, bg=BG,
                                          fg=DIM, width=12, anchor="e",
                                          font=(self.FONT,
                                                Typography.DETAIL_SIZE))
                    result_lbl.pack(side="right", padx=4)
                    chain.append(result_lbl)
                    probe_btn = FlatButton(
                        row, text="试调", variant="ghost",
                        font=(self.FONT, Typography.DETAIL_SIZE),
                        padx=6, pady=2,
                        on_click=lambda model=m: self._probe(model))
                    if m in self._probing:
                        probe_btn.config(state="disabled")
                    probe_btn.pack(side="right", padx=4, pady=2)
                    self.probe_btns[m] = probe_btn
                select_btn = FlatButton(
                    row, text="估算", variant="ghost",
                    font=(self.FONT, Typography.DETAIL_SIZE),
                    padx=6, pady=2)
                select_btn.pack(side="right", padx=(0, 4), pady=2)
                self._attach_tooltip(select_btn, "用于上方估算调用成本")
                select_btn.bind("<Button-1>",
                                lambda e, model=m: self._select_model(model),
                                add="+")
                # 之前整行 cursor="hand2" 却没有任何 hover 反馈,
                # 划过一整列模型看不出哪一行是可操作的。
                bind_hover_bg(chain,
                              lambda: to_tk_color(PALETTE.CARD_HOVER),
                              lambda: BG)
                hairline(row).pack(side="bottom", fill="x")

                for child in row.winfo_children():
                    child.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                    child.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                    child.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")
                row.bind("<Button-1>", lambda e, mid=m: self._drag_press(e, mid), add="+")
                row.bind("<B1-Motion>", lambda e, mid=m: self._drag_motion(e, mid), add="+")
                row.bind("<ButtonRelease-1>", lambda e, mid=m: self._drag_release(e, mid), add="+")

        try:
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(scroll_pos)
        except tk.TclError:
            pass
        # 行是刚重建的,重新打一遍滚轮 tag,否则悬停在新行上滚不动
        tag_subtree(self.inner, wheel_tag(self.inner))

    def _drag_press(self, event, mid):
        w = event.widget
        if isinstance(w, tk.Button):
            return
        try:
            if w.cget("text") in ("估算", "试调"):
                return
        except (tk.TclError, AttributeError):
            pass
        self._drag = {
            "mid": mid, "start_y": event.y_root,
            "active": False, "target": None, "indicator": None,
        }

    def _drag_motion(self, event, mid):
        d = getattr(self, "_drag", None)
        if not d or d["mid"] != mid:
            return
        if not d["active"]:
            if abs(event.y_root - d["start_y"]) <= 8:
                return
            d["active"] = True
            d["target"] = self._model_target_index(mid, event.y_root)
            self._show_model_indicator()
        if d["active"]:
            new_target = self._model_target_index(mid, event.y_root)
            if new_target != d["target"]:
                d["target"] = new_target
                self._show_model_indicator()

    def _drag_release(self, event, mid):
        d = getattr(self, "_drag", None)
        if not d or d["mid"] != mid:
            return
        if d["active"] and d["target"] is not None:
            self._commit_model_drag(mid, d["target"])
        self._clear_model_indicator()
        self._drag = None

    def _model_target_index(self, exclude_mid, y_root):
        rows = [w for w in self.inner.pack_slaves()
                if isinstance(w, tk.Frame) and hasattr(w, "_model_id")
                and w._model_id != exclude_mid]
        for i, w in enumerate(rows):
            try:
                top = w.winfo_rooty()
            except tk.TclError:
                continue
            mid_y = top + w.winfo_height() / 2
            if y_root < mid_y:
                return i
        return len(rows)

    def _show_model_indicator(self):
        self._clear_model_indicator()
        d = getattr(self, "_drag", None)
        if not d:
            return
        rows = [w for w in self.inner.pack_slaves()
                if isinstance(w, tk.Frame) and hasattr(w, "_model_id")
                and w._model_id != d["mid"]]
        indicator = tk.Frame(self.inner, height=Layout.DRAG_MARKER,
                             bg=to_tk_color(PALETTE.BLUE), bd=0,
                             highlightthickness=0)
        d["indicator"] = indicator
        idx = d["target"]
        if idx < len(rows):
            indicator.pack(fill="x", pady=0, before=rows[idx])
        else:
            indicator.pack(fill="x", pady=0)

    def _clear_model_indicator(self):
        d = getattr(self, "_drag", None)
        if d and d.get("indicator"):
            try:
                d["indicator"].destroy()
            except tk.TclError:
                pass
            d["indicator"] = None

    def _commit_model_drag(self, mid, new_index):
        if mid not in self.models:
            return
        # new_index 是**可见(过滤后)**列表里的下标 —— _model_target_index
        # 只遍历 inner 里渲染出来的行。直接拿它去插 self.models(全量)会把
        # 顺序写坏,而且 on_reorder 落盘的就是这个错序(用户只能自己重拖才能
        # 纠正)。所以先把可见域的重排算好,再按位置映射回全量。
        others = [m for m in self.models if m != mid]
        filtered = list(getattr(self, "filtered", None) or self.models)
        # 过滤是否生效(要在移除 mid **之前**比,否则长度天然差 1)
        filtering = len(filtered) != len(self.models) or \
            set(filtered) != set(self.models)
        vis = [m for m in filtered if m != mid]
        idx = max(0, min(new_index, len(vis)))
        new_vis = vis[:idx] + [mid] + vis[idx:]

        if not filtering:
            # 全部可见:索引域一致,直接用
            self.models = new_vis
        else:
            # 有条目被过滤掉:按"相邻的可见项"在**全量**列表里定位,
            # 而不是拿可见下标硬插(那会落到隐藏项的位置上,顺序全乱)。
            # 被过滤掉的条目自然保持原位。
            after = new_vis[idx + 1] if idx + 1 < len(new_vis) else None
            before = new_vis[idx - 1] if idx > 0 else None
            if after is not None and after in others:
                others.insert(others.index(after), mid)
            elif before is not None and before in others:
                others.insert(others.index(before) + 1, mid)
            else:
                others.append(mid)
            self.models = others
        if hasattr(self, "filtered"):
            self.filtered = list(new_vis)
        if self.on_reorder:
            try:
                self.on_reorder(list(self.models))
            except Exception:
                pass
        if self.on_after_reorder:
            try:
                self.on_after_reorder()
            except Exception:
                pass
        self._render()

    def _probe(self, model):
        if not self.on_probe:
            return
        # 同一模型在途时再点:两个请求竞速,结果标签互相覆盖,且双倍
        # 计费;禁用按钮 + 去重集合双保险
        if model in self._probing:
            return
        self._probing.add(model)
        btn = self.probe_btns.get(model)
        if btn is not None:
            try:
                btn.config(state="disabled")
            except tk.TclError:
                pass
        self._schedule_pump()
        threading.Thread(target=self._probe_worker, args=(model,),
                         daemon=True).start()

    def _schedule_pump(self):
        """在主线程排一个结果队列清理回调。窗口已销毁时静默放弃。"""
        if self._pump_scheduled:
            return
        self._pump_scheduled = True
        try:
            self.after(80, self._drain_probe_results)
        except tk.TclError:
            self._pump_scheduled = False

    def _drain_probe_results(self):
        self._pump_scheduled = False
        try:
            while True:
                model, ok, lat, err = self._probe_results.get_nowait()
                self._probe_done(model, ok, lat, err)
        except queue.Empty:
            pass
        if self._probing or not self._probe_results.empty():
            self._schedule_pump()

    def _select_model(self, model):
        self._last_selected = model
        self.calc_cost_var.set(_estimate_cost(model, self.calc_n_var.get()))

    def _on_calc_change(self):
        sel = getattr(self, "_last_selected", None)
        if sel:
            self.calc_cost_var.set(_estimate_cost(sel, self.calc_n_var.get()))

    def _probe_worker(self, model):
        try:
            ok, latency_ms, error = self.on_probe(model)
        except Exception as e:
            ok, latency_ms, error = False, 0, str(e)
        # tkinter 的 after/createcommand 不允许在工作线程调用
        # (RuntimeError: main thread is not in main loop),原实现只捕
        # TclError:试调结果静默丢失,按钮/标签永远不更新。结果进队列,
        # 主线程经 _drain_probe_results 取走。
        self._probe_results.put((model, ok, latency_ms, error))

    def _probe_done(self, model, ok, latency_ms, error):
        self._probing.discard(model)
        btn = self.probe_btns.get(model)
        if btn is not None:
            try:
                btn.config(state="normal")
            except tk.TclError:
                pass
        mark = "✓" if ok else "✗"
        msg = f"{mark} {latency_ms:.0f}ms" if ok else f"✗ {error}"
        var = (getattr(self, "probe_result_vars", None) or {}).get(model)
        if var is not None:
            var.set(msg)
            self.after(3000, lambda: self._clear_probe_result(var)
                       if var.get() == msg else None)

    def _clear_probe_result(self, var):
        try:
            var.set("")
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfig(self._list_window, width=event.width)
        except tk.TclError:
            pass

    def _on_wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    def _wheel_enter(self, event):
        """已废弃:滚轮改由 bind_wheel_tree 常驻挂在 inner 子树上。

        旧的 <Enter>/<Leave> + bind_all 组合在移出列表时会走
        unbind_all(sequence, funcid),而 tkinter 的 unbind_all 只接受一个
        参数 → TypeError;而且没摘干净的全局绑定会连主面板的滚轮一起抢走。
        """
        return None

    def _wheel_leave(self, event=None):
        unbind = getattr(self, "_unbind_wheel", None)
        if unbind is None:
            return
        try:
            unbind()
        except tk.TclError:
            pass
        self._unbind_wheel = None

    def _grab_when_viewable(self, e=None):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _on_close(self):
        self._wheel_leave()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _attach_tooltip(self, widget, text, delay_ms=600):
        """委托共享实现。原来这里是 model_panel 的私有副本,少了
        <Destroy> 绑定,列表重渲染后弹窗留在已销毁的父窗口上。"""
        from ui.tooltip import attach
        return attach(widget, lambda: text, delay_ms=delay_ms, owner=self)


# 常见模型公开价(USD per 1M tokens),粗略。生产环境应从 provider /pricing 端点拉。
PRICE_TABLE = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4-turbo": (10.0, 30.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-3-opus": (15.0, 75.0),
    "deepseek-chat": (0.27, 1.1),
    "deepseek-reasoner": (0.55, 2.19),
    "glm-4-plus": (7.0, 7.0),
    "glm-4-flash": (0.0, 0.0),
}


def _estimate_cost(model, n_calls):
    try:
        n = int(n_calls or 0)
    except ValueError:
        return "次数无效"
    if n <= 0:
        return "—"
    mid = model.lower()
    matched = None
    for key, price in PRICE_TABLE.items():
        if key in mid or mid in key:
            matched = price
            break
    if matched is None:
        return f"无价表 (需手填)"
    in_p, out_p = matched
    avg_in, avg_out = 500, 200
    cost = (in_p * avg_in + out_p * avg_out) / 1_000_000 * n
    return f"≈ ${cost:.4f}"
