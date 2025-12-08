import random

class AlgoState:
    """单个算法的独立状态机"""
    def __init__(self, name, memory_blocks):
        self.name = name
        self.memory_blocks = memory_blocks
        self.memory = [None] * memory_blocks
        
        # 统计数据
        self.miss_count = 0
        self.total_count = 0
        self.write_back_count = 0
        
        # 辅助变量
        self.load_counter = 0   # FIFO
        self.clock_hand = 0     # Clock
        
    def process(self, page_id, op_type, current_time, future_pages=None):
        """
        处理一次内存访问
        """
        self.total_count += 1

         # 1. 查找页面
        hit_idx = -1
        for i, frame in enumerate(self.memory):
            if frame is not None and frame['page'] == page_id:
                hit_idx = i
                break
        
        if hit_idx != -1:
            return self._handle_hit(hit_idx, op_type, current_time)
        else:
            return self._handle_miss(page_id, op_type, current_time, future_pages)
    
    def _handle_hit(self, idx, op_type, current_time):
        """处理命中逻辑"""
        frame = self.memory[idx]
        frame['last_access'] = current_time
        
        # 算法特定行为
        if self.name == "LINUX":
            frame['ref_bit'] = 1
        elif self.name == "LINUX_NG":
            if not frame.get('is_active_list', False):
                frame['is_active_list'] = True
            self._balance_lists()

        # 脏页标记
        if op_type == 'W':
            frame['dirty'] = True
            
        return {"status": "Hit", "swapped": None, "is_write_back": False}

    def _handle_miss(self, page_id, op_type, current_time, future_pages):
        """处理缺页逻辑"""
        self.miss_count += 1
        self.load_counter += 1
        is_write_back = False
        swapped_out = None
        
        # 创建新页帧
        new_frame = {
            "page": page_id,
            "loaded_at": self.load_counter,
            "last_access": current_time,
            "ref_bit": 1,
            "dirty": (op_type == 'W'),
            "is_active_list": False # 默认为 Inactive
        }
        
        # 1. 尝试寻找空闲位
        target_idx = -1
        for i in range(self.memory_blocks):
            if self.memory[i] is None:
                target_idx = i
                break
        
        # 2. 如果没空位，执行置换
        if target_idx == -1:
            target_idx = self._get_victim(future_pages)
            victim_frame = self.memory[target_idx]
            swapped_out = victim_frame['page']
            
            if victim_frame.get('dirty', False):
                self.write_back_count += 1
                is_write_back = True

        # 3. 装入新页
        self.memory[target_idx] = new_frame
        
        # Linux Clock 算法特殊处理：装入后指针下移
        if self.name == "LINUX":
            self.clock_hand = (target_idx + 1) % self.memory_blocks
            
        return {"status": "Miss", "swapped": swapped_out, "is_write_back": is_write_back}

    def _balance_lists(self):
        """[LINUX_NG] 维护 Active/Inactive 列表平衡"""
        active_frames = [f for f in self.memory if f and f.get('is_active_list')]
        if len(active_frames) > self.memory_blocks // 2:
            victim = min(active_frames,key = lambda x:x['last_access'])
            victim['is_active_list'] = False

    def _get_victim(self, future_pages=None):
        valid_frames = [f for f in self.memory if f is not None]
        if not valid_frames: return 0

        if self.name == "FIFO":
            victim = min(valid_frames, key=lambda x: x['loaded_at'])
            return self.memory.index(victim)
        
        elif self.name == "LRU":
            victim = min(valid_frames, key=lambda x: x['last_access'])
            return self.memory.index(victim)
        
        elif self.name == "OPT":
            return self._get_opt_victim(future_pages)
        elif self.name == "LINUX":
           return self._run_clock_algorithm()
        elif self.name == "LINUX_NG":
            # 优先淘汰 Inactive，若无则淘汰全局 LRU
            inactive = [f for f in valid_frames if not f.get('is_active_list', False)]
            pool = inactive if inactive else valid_frames
            victim = min(pool, key=lambda x: x['last_access'])
            return self.memory.index(victim)
        
        return 0

    def _get_opt_victim(self, future_pages):
        """OPT 算法专用逻辑"""
        if future_pages is None: return 0
        max_dist = -1
        victim_idx = -1
        for i, frame in enumerate(self.memory):
            try:
                dist = future_pages.index(frame['page'])
            except ValueError:
                dist = 99999
            if dist > max_dist:
                max_dist = dist
                victim_idx = i
        return victim_idx

    def _run_clock_algorithm(self, dry_run=False):
        """Clock 算法核心逻辑 (支持 dry_run 用于预测)"""
        temp_hand = self.clock_hand
        # 防止死循环：最多遍历 2 圈 + 1
        for _ in range(self.memory_blocks * 2 + 1):
            frame = self.memory[temp_hand]
            if frame['ref_bit'] == 1:
                if not dry_run: frame['ref_bit'] = 0
                temp_hand = (temp_hand + 1) % self.memory_blocks
            else:
                victim_idx = temp_hand
                if not dry_run:
                    self.clock_hand = (temp_hand + 1) % self.memory_blocks
                return victim_idx
        return temp_hand

    def predict_next_victim(self, future_pages=None):
        """预测下一个受害者"""
        if None in self.memory: return -1
        
        if self.name == "LINUX":
            temp_hand = self.clock_hand
            for _ in range(self.memory_blocks * 2):
                if self.memory[temp_hand]['ref_bit'] == 0:
                    return temp_hand
                temp_hand = (temp_hand + 1) % self.memory_blocks
            return temp_hand
        else:
            return self._get_victim(future_pages)

    def get_snapshot(self, current_time):
        """
        生成用于 UI 显示的快照数据
        将“如何显示数据”的逻辑内聚在 Model 内部
        """
        snapshot = []
        for i, f in enumerate(self.memory):
            if f is None:
                snapshot.append(None)
                continue
                
            # 生成元数据文本
            meta = ""
            if self.name == "FIFO": 
                meta = f"SEQ:{f['loaded_at']}"
            elif self.name == "LRU": 
                meta = f"IDLE:{current_time - f['last_access']}"
            elif self.name == "LINUX": 
                meta = f"REF:{f['ref_bit']}"
            elif self.name == "LINUX_NG":
                list_name = "ACT" if f.get('is_active_list') else "INA"
                meta = f"{list_name}:{current_time - f['last_access']}"
            elif self.name == "OPT": 
                meta = "OPT"
            
            # 脏页覆盖显示
            if f.get('dirty'): meta = "DIRTY"
            
            snapshot.append({
                "page": f['page'],
                "meta": meta,
                "is_hand": (self.name == "LINUX" and i == self.clock_hand),
                "is_dirty": f.get('dirty', False),
                "is_active_list": f.get('is_active_list', False)
            })
        return snapshot

class PageManager:
    """总控制器：管理指令流和多算法状态"""
    def __init__(self, total_instructions=2000, total_pages=32, memory_blocks=4):
        self.total_instructions = total_instructions
        self.memory_blocks = memory_blocks
        self.total_pages = total_pages
        self.algos = {
            name: AlgoState(name, memory_blocks) 
            for name in ["FIFO", "LRU", "OPT", "LINUX", "LINUX_NG"]
        }
        self.reset()
    
    def _generate_instructions(self):
        """生成指令序列：20%冷数据 + 80%热点数据"""
        insts = []
        for _ in range(self.total_instructions):
            rand_val = random.random()
            if rand_val < 0.8:
                hot_inst = random.randint(0, 39)
                insts.append((hot_inst, 'W' if random.random() < 0.5 else 'R'))
            else:
                cold_inst = random.randint(40, 200) 
                insts.append((cold_inst, 'W' if random.random() < 0.1 else 'R')) # 冷数据通常读多写少
        
        return insts[:self.total_instructions]

    def load_belady_sequence(self):
        """加载 Belady 异常经典序列"""
        self.mode = "BELADY"
        pages = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
        self.instructions = [(p * 10, 'R') for p in pages] 
        self.current_inst_idx = 0
        self.reset_algos()

    def step(self):
        """执行单步模拟"""
        if self.current_inst_idx >= len(self.instructions):
            return None

        addr, op_type = self.instructions[self.current_inst_idx]
        page_id = addr // 10
        self.current_time += 1
        
        # 仅为 OPT 算法准备未来数据 (按需计算)
        future_pages = None

        step_results = {}
        for name, algo in self.algos.items():
            if name == "OPT" and future_pages is None:
                future_tuples = self.instructions[self.current_inst_idx+1:]
                future_pages = [x[0] // 10 for x in future_tuples]

            res = algo.process(page_id, op_type, self.current_time, future_pages)
            miss_rate = (algo.miss_count / algo.total_count) * 100 if algo.total_count > 0 else 0
            step_results[name] = {
                "status": res["status"],
                "swapped": res["swapped"],
                "is_write_back": res["is_write_back"],
                "miss_rate": miss_rate,
                "miss_count": algo.miss_count,
                "wb_count": algo.write_back_count
            }

        self.current_inst_idx += 1
        
        # 获取当前视图算法的 UI 数据
        view_algo = self.algos[self.view_algo_name]

        # 预测高亮 (同样按需计算)
        pred_future = future_pages if self.view_algo_name == "OPT" else None
        if self.view_algo_name == "OPT" and pred_future is None:
            future_tuples = self.instructions[self.current_inst_idx:]
            pred_future = [x[0] // 10 for x in future_tuples]

        next_victim = view_algo.predict_next_victim(pred_future)
        mem_view = view_algo.get_snapshot(self.current_time)

        return {
            "inst": addr,
            "op": op_type,
            "page": page_id,
            "results": step_results,
            "view_algo": self.view_algo_name,
            "memory": mem_view,
            "next_victim": next_victim,
            "current_step": self.current_inst_idx
        }

    def reset(self):
        self.current_inst_idx = 0
        self.current_time = 0
        self.mode = "NORMAL"
        self.view_algo_name = "FIFO"
        self.instructions = self._generate_instructions()
        self.reset_algos()
        
    def reset_algos(self):
        for algo in self.algos.values():
            algo.__init__(algo.name, self.memory_blocks)