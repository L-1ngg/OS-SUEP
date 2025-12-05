import math
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Button, Log, Label, Input
from textual.reactive import reactive
from textual_plotext import PlotextPlot

# 导入逻辑层
from memory_model import PageManager

class AlgoStatCard(Static):
    def __init__(self, algo_name):
        super().__init__(id=f"card-{algo_name.lower()}")
        self.algo_name = algo_name

    def compose(self) -> ComposeResult:
        yield Label(self.algo_name, classes="card-title")
        yield Label("0.0%", classes="card-rate")
        yield Label("WB: 0", classes="card-wb")
        yield Label("--", classes="card-status")

class MemBlock(Static):
    frame_idx = reactive("0")
    page_num = reactive("--")
    meta_info = reactive("")
    
    def compose(self) -> ComposeResult:
        yield Label(f"#{self.frame_idx}", classes="mem-idx")
        yield Label(self.page_num, classes="mem-page")
        yield Label(self.meta_info, classes="mem-meta")

class MemSimApp(App):
    # 指向独立的 CSS 文件
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("space", "toggle", "Start/Pause"),
        ("r", "reset", "Reset"),
        ("ctrl+c", "quit", "Quit")
    ]

    def __init__(self):
        super().__init__()
        self.current_blocks = 4
        # 实例化逻辑层
        self.logic = PageManager(memory_blocks=self.current_blocks)
        self.timer = None
        self.sim_running = False 
        self.plot_data_x = []
        self.plot_data_y = []
        self.mem_block_refs = []

    def compose(self) -> ComposeResult:
        yield Label("Virtual Memory Simulator: Dirty Bits & Belady Anomaly", classes="app-title")
        
        with Container(id="stats-panel"):
            yield AlgoStatCard("FIFO")
            yield AlgoStatCard("LRU")
            yield AlgoStatCard("OPT")
            yield AlgoStatCard("LINUX")
            
        with Container(id="controls-panel"):
            with Container(id="setting-row"):
                yield Label("RAM (1-10):")
                yield Input(placeholder="4", value="4", type="integer", id="input-size")
            
            with Container(id="algo-buttons"):
                yield Button("FIFO", id="btn-fifo", variant="primary")
                yield Button("LRU", id="btn-lru", variant="default")
                yield Button("OPT", id="btn-opt", variant="default")
                yield Button("LINUX", id="btn-linux", variant="default")
            
            with Container(classes="action-row"):
                yield Button("START", id="btn-start", variant="success")
                yield Button("BELADY", id="btn-belady", variant="error")
            
        with Container(id="log-panel"):
            with Container(id="chart-container"):
                yield PlotextPlot(id="miss-chart-plot")
            yield Log(id="sys-log")
            
        yield Container(id="memory-panel")

        yield Footer()

    async def on_mount(self):
        self.query_one("#sys-log").write_line("System Initialized.")
        self.update_active_card("FIFO")
        self.init_chart()
        await self.change_memory_size(self.current_blocks)

    def init_chart(self):
        plt = self.query_one("#miss-chart-plot", PlotextPlot).plt
        plt.title("Miss Rate Trend") 
        plt.theme("pro")
        plt.xlabel("") 
        plt.ylabel("Miss %")
        plt.ylim(0, 100)

    async def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "input-size":
            try:
                if not event.value: return 
                val = int(event.value)
                if 1 <= val <= 10:
                    await self.change_memory_size(val)
                else:
                    self.query_one("#sys-log").write_line("[red]Error: Size must be 1-10[/]")
            except ValueError:
                pass

    async def change_memory_size(self, size):
        self.sim_running = False
        if self.timer: self.timer.stop()
        self.current_blocks = size
        
        self.query_one("#sys-log").write_line(f"Resizing to {size} blocks...")
        self.logic = PageManager(memory_blocks=size)
        if self.logic.mode == "BELADY":
            self.logic.load_belady_sequence()
        
        panel = self.query_one("#memory-panel")
        await panel.remove_children()
        
        self.mem_block_refs = [MemBlock() for _ in range(size)]
        await panel.mount(*self.mem_block_refs)
        
        self.update_memory_grid_layout(size)
        
        self.plot_data_x = []
        self.plot_data_y = []
        self.refresh_chart()
        self.update_ui_reset()
        
        self.query_one("#btn-start").label = "START"
        self.query_one("#btn-start").remove_class("pause")

    def update_memory_grid_layout(self, count):
        cols = 2
        if count > 2: cols = 2
        if count > 4: cols = 2 
        if count > 6: cols = 3 
        rows = math.ceil(count / cols)
        panel = self.query_one("#memory-panel")
        panel.styles.grid_size_columns = cols
        panel.styles.grid_size_rows = rows

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "btn-start":
            self.action_toggle()
        elif bid == "btn-belady":
            self.start_belady_demo()
        elif bid in ["btn-fifo", "btn-lru", "btn-opt", "btn-linux"]:
            algo = bid.split("-")[1].upper()
            self.set_view_algorithm(algo)

    def start_belady_demo(self):
        self.sim_running = False
        if self.timer: self.timer.stop()
        
        self.set_view_algorithm("FIFO")
        self.logic.load_belady_sequence()
        
        self.plot_data_x = []
        self.plot_data_y = []
        self.refresh_chart()
        self.update_ui_reset()
        self.query_one("#sys-log").clear()
        self.query_one("#sys-log").write_line("[bold magenta]=== Belady's Anomaly Demo ===[/]")
        self.query_one("#sys-log").write_line("Seq: 1,2,3,4,1,2,5,1,2,3,4,5")
        self.query_one("#sys-log").write_line("1. Set RAM to 3 -> Run -> Check Faults (Expected: 9)")
        self.query_one("#sys-log").write_line("2. Set RAM to 4 -> Run -> Check Faults (Expected: 10)")
        
        self.query_one("#btn-start").label = "START"
        self.query_one("#btn-start").remove_class("pause")

    def set_view_algorithm(self, algo):
        self.logic.view_algo_name = algo
        self.query_one("#sys-log").write_line(f"View: {algo}")
        for b in ["fifo", "lru", "opt", "linux"]:
            variant = "primary" if b.upper() == algo else "default"
            self.query_one(f"#btn-{b}").variant = variant
        self.update_active_card(algo)
        self.plot_data_x = []
        self.plot_data_y = []
        self.refresh_chart()

    def update_active_card(self, active_algo):
        for algo in ["FIFO", "LRU", "OPT", "LINUX"]:
            card = self.query_one(f"#card-{algo.lower()}")
            if algo == active_algo:
                card.add_class("card-active")
            else:
                card.remove_class("card-active")

    def action_toggle(self):
        self.sim_running = not self.sim_running
        btn = self.query_one("#btn-start")
        if self.sim_running:
            btn.label = "PAUSE"
            btn.add_class("pause")
            interval = 0.01
            self.timer = self.set_interval(interval, self.step_simulation)
        else:
            btn.label = "RESUME"
            btn.remove_class("pause")
            if self.timer: self.timer.stop()

    async def action_reset(self):
        await self.change_memory_size(self.current_blocks)

    def refresh_chart(self):
        plot_widget = self.query_one("#miss-chart-plot", PlotextPlot)
        plt = plot_widget.plt
        plt.clear_data()
        if self.plot_data_x:
            plt.plot(self.plot_data_x, self.plot_data_y, color="red", marker="dot")
        plot_widget.refresh()

    def step_simulation(self):
        res = self.logic.step()
        if res is None:
            self.sim_running = False
            self.timer.stop()
            self.query_one("#btn-start").label = "FINISHED"
            self.query_one("#btn-start").remove_class("pause")
            
            # 使用逻辑层的状态来检查 Belady 结果
            if self.logic.mode == "BELADY" and self.logic.view_algo_name == "FIFO":
                misses = self.logic.algos["FIFO"].miss_count
                blocks = self.current_blocks
                self.query_one("#sys-log").write_line(f"[magenta]Result: {blocks} Blocks -> {misses} Misses[/]")
            
            return

        current_algo_res = None
        for name, data in res["results"].items():
            card = self.query_one(f"#card-{name.lower()}")
            card.query_one(".card-rate").update(f"{data['miss_rate']:.1f}%")
            card.query_one(".card-wb").update(f"WB: {data['wb_count']}")
            status_lbl = card.query_one(".card-status")
            status_lbl.update(data['status'])
            status_lbl.classes = "card-status status-miss" if data['status'] == "Miss" else "card-status status-hit"
            if name == res["view_algo"]:
                current_algo_res = data

        if current_algo_res:
            self.plot_data_x.append(res['current_step'])
            self.plot_data_y.append(current_algo_res["miss_rate"])
            if len(self.plot_data_x) > 60:
                self.plot_data_x.pop(0)
                self.plot_data_y.pop(0)
            self.refresh_chart()

        victim_idx = res["next_victim"]
        mem_data = res["memory"]
        limit = min(len(self.mem_block_refs), len(mem_data))
        
        for i in range(limit):
            block = self.mem_block_refs[i]
            data = mem_data[i]
            
            block.query_one(".mem-idx").update(f"#{i}")
            
            if data is not None:
                block.query_one(".mem-page").update(str(data["page"]))
                block.query_one(".mem-meta").update(data["meta"])
                
                base_classes = "block-active"
                if i == victim_idx:
                    base_classes += " victim-frame"
                elif data.get("is_dirty"):
                    base_classes += " block-dirty"
                elif data.get("is_hand"):
                    base_classes += " clock-hand-frame"
                
                block.classes = base_classes
            else:
                block.query_one(".mem-page").update("--")
                block.query_one(".mem-meta").update("EMPTY")
                block.classes = "block-empty"

        if current_algo_res["status"] == "Miss":
            op_str = "[blue]WRITE[/]" if res["op"] == 'W' else "READ"
            status_str = f"[red]{current_algo_res['status']}[/]" 
            msg = f"[{res['view_algo']}] {status_str} | {op_str} Pg {res['page']}"
            if current_algo_res["swapped"] is not None:
                msg += f" -> Swap {current_algo_res['swapped']}"
                if current_algo_res["is_write_back"]:
                    msg += " [bold yellow](WRITE BACK)[/]"
            self.query_one("#sys-log").write_line(msg)

    def update_ui_reset(self):
        for algo in ["FIFO", "LRU", "OPT", "LINUX"]:
            card = self.query_one(f"#card-{algo.lower()}")
            card.query_one(".card-rate").update("0.0%")
            card.query_one(".card-wb").update("WB: 0")
            card.query_one(".card-status").update("--")