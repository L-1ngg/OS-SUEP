import math
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Static, Button, RichLog, Label, Input,Log
from textual.reactive import reactive
from textual_plotext import PlotextPlot
from textual.events import Blur, Click  # 关键：引入 Click 事件

# 导入逻辑层
from memory_model import PageManager

# === SUEP ASCII LOGO ===
SUEP_LOGO = r"""
    ____  _   _ _____ ____  
   / ___|| | | | ____|  _ \ 
   \___ \| | | |  _| | |_) |
    ___) | |_| | |___|  __/ 
|____/ \___/|_____|_| 
"""

class SmartInput(Input):
    """
    智能输入框：失去焦点时自动提交。
    """
    def on_blur(self, event: Blur) -> None:
        self.post_message(self.Submitted(self, self.value))

class AlgoStatCard(Static):
    """
    算法统计卡片组件
    负责显示单个算法的缺页率、写回数和状态
    """
    def __init__(self, algo_name):
        # 自动处理 ID 格式化
        super().__init__(id=f"card-{algo_name.lower().replace('+','p')}")
        self.algo_name = algo_name

    def compose(self) -> ComposeResult:
        yield Label(self.algo_name, classes="card-title")
        yield Label("0.0%", classes="card-rate")
        yield Label("WB: 0", classes="card-wb")
        yield Label("--", classes="card-status")

    def update_data(self, miss_rate: float, wb_count: int, status: str):
        """更新卡片数据 (封装了内部组件的操作)"""
        self.query_one(".card-rate").update(f"{miss_rate:.1f}%")
        self.query_one(".card-wb").update(f"WB: {wb_count}")
        
        status_lbl = self.query_one(".card-status")
        status_lbl.update(status)
        
        # 动态样式
        status_lbl.classes = "card-status status-miss" if status == "Miss" else "card-status status-hit"

    def reset(self):
        """重置显示"""
        self.update_data(0.0, 0, "--")

    def set_active(self, is_active: bool):
        """设置是否为当前观看的算法"""
        if is_active:
            self.add_class("card-active")
        else:
            self.remove_class("card-active")


class MemBlock(Static):
    """
    内存块组件
    负责根据传入的状态字典，自我渲染样式和文字
    """
    frame_idx = reactive("0")
    page_num = reactive("--")
    meta_info = reactive("")
    
    def compose(self) -> ComposeResult:
        yield Label(f"#{self.frame_idx}", classes="mem-idx")
        yield Label(self.page_num, classes="mem-page")
        yield Label(self.meta_info, classes="mem-meta")
    
    def update_state(self, idx: int, data: dict, is_victim: bool, view_algo_name: str):
        """
        根据逻辑层传来的数据更新自身的视图
        """
        # 更新帧号 (始终显示)
        self.query_one(".mem-idx").update(f"#{idx}")

        # 清除所有旧的状态类
        self.classes = ""

        if data is None:
            # 空闲状态
            self.query_one(".mem-page").update("--")
            self.query_one(".mem-meta").update("EMPTY")
            self.add_class("block-empty")
            return

        # 有数据状态
        self.query_one(".mem-page").update(str(data["page"]))
        self.query_one(".mem-meta").update(data["meta"])

        self.add_class("block-active")
        # 计算优先级最高的 CSS 样式类
        if is_victim:
            self.add_class("victim-frame")
        elif data.get("is_dirty"):
            self.add_class("block-dirty")
        elif data.get("is_active_list"): # Modern Linux Active
            self.add_class("block-list-active")
        elif data.get("is_hand"):
            self.add_class("clock-hand-frame")
        elif view_algo_name == "LINUX_NG": # Modern Linux Inactive
            self.add_class("block-list-inactive")


# ==========================================
# 主程序 (Main App)
# ==========================================

class MemSimApp(App):
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("space", "toggle", "Start/Pause"),
        ("r", "reset", "Reset"),
        ("ctrl+c", "quit", "Quit"),
        ("q", "quit", "Quit")
    ]

    def __init__(self):
        super().__init__()
        self.current_blocks = 4
        self.logic = PageManager(memory_blocks=self.current_blocks)
        self.timer = None
        self.sim_running = False 
        self.plot_data_x = []
        self.plot_data_y = []
        self.mem_block_refs = []

        self.algo_names = ["FIFO", "LRU", "OPT", "LINUX", "LINUX_NG"]
        self.algo_histories = {
            name: {'x': [], 'y': []} 
            for name in self.algo_names
        }

    def compose(self) -> ComposeResult:
        yield Label("Virtual Memory Simulator", classes="app-title")
        
        with Container(id="stats-panel"):
            yield AlgoStatCard("FIFO")
            yield AlgoStatCard("LRU")
            yield AlgoStatCard("OPT")
            yield AlgoStatCard("LINUX")
            yield AlgoStatCard("LINUX_NG")
            
        with Container(id="controls-panel"):
            with Container(id="setting-row"):
                yield Label("RAM (1-10):")
                yield SmartInput(placeholder="4", value="4", type="integer", id="input-size")
            
            with Container(id="algo-buttons"):
                yield Button("FIFO", id="btn-fifo", variant="primary")
                yield Button("LRU", id="btn-lru", variant="default")
                yield Button("OPT", id="btn-opt", variant="default")
                yield Button("CLOCK", id="btn-linux", variant="default")
                yield Button("LNX+", id="btn-linux_ng", variant="default")
            
            with Container(classes="action-row"):
                yield Button("START", id="btn-start", variant="success")
                yield Button("BELADY", id="btn-belady", variant="error")
            
        with Container(id="log-panel"):
            yield Label(SUEP_LOGO,classes="logo")
            with Container(id="chart-container"):
                yield PlotextPlot(id="miss-chart-plot")
            yield RichLog(id="sys-log",markup=True,wrap=True)
            
        yield Container(id="memory-panel")
        yield Footer()

    async def on_mount(self):
        self.query_one("#sys-log").write("System Initialized.")
        self.update_active_card_highlight("FIFO")
        self.init_chart()
        await self.change_memory_size(self.current_blocks)

    def init_chart(self):
        plt = self.query_one("#miss-chart-plot", PlotextPlot).plt
        plt.title("Miss Rate Trend") 
        plt.theme("pro")
        plt.xlabel("") 
        plt.ylabel("Miss %")
        plt.ylim(0, 100)

    # === 全局点击事件处理 ===
    def on_click(self, event: Click) -> None:
        """全局点击处理：点击非交互区时让输入框失焦"""
        focused = self.focused
        if focused and focused.id == "input-size":
            if event.widget != focused and not event.widget.can_focus:
                self.set_focus(None)

    async def on_input_submitted(self, event: Input.Submitted):
        """处理内存大小修改"""
        if event.input.id == "input-size":
            try:
                if not event.value: return 
                val = int(event.value)
                if val == self.current_blocks: return

                if 1 <= val <= 10:
                    await self.change_memory_size(val)
                else:
                    self.query_one("#sys-log").write("[red]Error: Size must be 1-10[/]")
                    event.input.value = str(self.current_blocks)
            except ValueError:
                pass

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "btn-start":
            self.action_toggle()
        elif bid == "btn-belady":
            self.start_belady_demo()
        elif bid.startswith("btn-"): # 算法按钮
            algo_tag = bid.replace("btn-", "").upper()
            self.set_view_algorithm(algo_tag)


    # === 业务逻辑 ===
    async def change_memory_size(self, size):
        self._stop_simulation()
        self.current_blocks = size
        self.query_one("#sys-log").write(f"Resizing to {size} blocks...")
        
        # 重置逻辑层
        self.logic = PageManager(memory_blocks=size)
        if self.logic.mode == "BELADY":
            self.logic.load_belady_sequence()
        
        # 重建内存块 UI
        panel = self.query_one("#memory-panel")
        await panel.remove_children()
        self.mem_block_refs = [MemBlock() for _ in range(size)]
        await panel.mount(*self.mem_block_refs)
        
        self.update_memory_grid_layout(size)
        
        # 重置图表和状态
        self.plot_data_x = []
        self.plot_data_y = []
        self.refresh_chart()
        self.update_ui_reset()

    def update_memory_grid_layout(self, count):
        cols = 2 if count <= 4 else (3 if count <= 6 else 4)
        rows = math.ceil(count / cols)
        panel = self.query_one("#memory-panel")
        panel.styles.grid_size_columns = cols
        panel.styles.grid_size_rows = rows

    def start_belady_demo(self):
        self._stop_simulation()
        self.set_view_algorithm("FIFO")
        self.logic.load_belady_sequence()
        self.reset_views()
        
        log = self.query_one("#sys-log")
        log.clear()
        log.write("[bold magenta]=== Belady's Anomaly Demo ===[/]")
        log.write("Seq: 1,2,3,4,1,2,5,1,2,3,4,5")
        log.write("1. Set RAM to 3 -> Run -> Check Faults (Expected: 9)")
        log.write("2. Set RAM to 4 -> Run -> Check Faults (Expected: 10)")

    def set_view_algorithm(self, algo):
        self.logic.view_algo_name = algo
        self.query_one("#sys-log").write(f"View: {algo}")

        for b_id in ["btn-fifo", "btn-lru", "btn-opt", "btn-linux", "btn-linux_ng"]:
            btn = self.query_one(f"#{b_id}")
            suffix = b_id.replace("btn-","").upper();
            btn.variant = "primary" if suffix == algo else "default"

        self.update_active_card_highlight(algo)
        self.plot_data_x = []
        self.plot_data_y = []
        self.refresh_chart()

    def update_active_card_highlight(self, active_algo):
        for algo in ["FIFO", "LRU", "OPT", "LINUX", "LINUX_NG"]:
            # 处理特殊 ID 字符
            card_id = f"#card-{algo.lower().replace('+', 'p')}"
            try:
                card = self.query_one(card_id, AlgoStatCard)
                card.set_active(algo == active_algo)
            except:
                pass

    def action_toggle(self):
        self.sim_running = not self.sim_running
        btn = self.query_one("#btn-start")
        if self.sim_running:
            btn.label = "PAUSE"
            btn.add_class("pause")
            self.timer = self.set_interval(0.01, self.step_simulation)
        else:
            btn.label = "RESUME"
            btn.remove_class("pause")
            if self.timer: self.timer.stop()

    def _stop_simulation(self):
        """辅助方法：完全停止模拟并重置按钮"""
        self.sim_running = False
        if self.timer: self.timer.stop()
        btn = self.query_one("#btn-start")
        btn.label = "START"
        btn.remove_class("pause")

    def reset_views(self):
        # 重置所有算法的历史数据
        for name in self.algo_names:
            self.algo_histories[name] = {'x': [], 'y': []}

        self.refresh_chart()
        self.update_ui_reset()


    def refresh_chart(self):
        plot_widget = self.query_one("#miss-chart-plot", PlotextPlot)
        plt = plot_widget.plt
        plt.clear_data()

        current_algo = self.logic.view_algo_name
        data = self.algo_histories.get(current_algo, {'x':[], 'y':[]})
        
        if data['x']:
            plt.plot(data['x'], data['y'], color="red", marker="dot")

        plot_widget.refresh()

    def step_simulation(self):
        res = self.logic.step()
        if res is None:
            self._stop_simulation()
            self.query_one("#btn-start").label = "FINISHED"
            self.query_one("#btn-start").remove_class("pause")
            
            # Belady 结果检查
            if self.logic.mode == "BELADY" and self.logic.view_algo_name == "FIFO":
                misses = self.logic.algos["FIFO"].miss_count
                self.query_one("#sys-log").write(f"[magenta]Result: {self.current_blocks} Blocks -> {misses} Misses[/]")
            return
        
        # 1. 批量更新统计卡片
        current_algo_res = None
        for name, data in res["results"].items():
            card_id = f"#card-{name.lower().replace('+', 'p')}"
            try:
                card = self.query_one(card_id, AlgoStatCard)
                card.update_data(data['miss_rate'], data['wb_count'], data['status'])
            except:
                pass

            # === 并行记录每个算法的绘图数据 ===    
            hist = self.algo_histories[name]
            hist['x'].append(res['current_step'])
            hist['y'].append(data['miss_rate'])
             # 限制数据长度，防止无限增长
            if len(hist['x']) > 60:
                hist['x'].pop(0)
                hist['y'].pop(0)
            
            if name == res["view_algo"]:
                current_algo_res = data

        # 2. 刷新图表 (显示当前选定算法的数据)
        self.refresh_chart()

        # 3. 批量更新内存块 (调用组件封装的方法)
        victim_idx = res["next_victim"]
        mem_data = res["memory"]
        limit = min(len(self.mem_block_refs), len(mem_data))
        
        for i in range(limit):
            block = self.mem_block_refs[i]
            data = mem_data[i]
            is_victim = (i == victim_idx)
            block.update_state(i, data, is_victim, self.logic.view_algo_name)

        # 4. 打印日志
        status_str = ""
        if current_algo_res["status"] == "Miss":
            status_str = f"[red]Miss[/]"
        else:
            status_str = f"[green]HIT [/]"
        
        op_str = "[blue]WRITE[/]" if res["op"] == 'W' else "READ "
        msg = f"[{res['view_algo']}] {status_str} | {op_str} Pg {res['page']}"

        if current_algo_res["swapped"] is not None:
            msg += f" -> Swap {current_algo_res['swapped']}"
            if current_algo_res["is_write_back"]:
                msg += " [bold yellow](WRITE BACK)[/]"
        self.query_one("#sys-log").write(msg)


    def update_ui_reset(self):
        """重置所有卡片"""
        for algo in ["FIFO", "LRU", "OPT", "LINUX", "LINUX_NG"]:
            card_id = f"#card-{algo.lower().replace('+', 'p')}"
            try:
                self.query_one(card_id, AlgoStatCard).reset()
            except:
                pass
