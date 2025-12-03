import random

class AlgoState:
    """单个算法的独立状态机"""
    def __init__(self, name, memory_blocks):
        self.name = name
        self.memory_blocks = memory_blocks
        # memory: [{"page": int, "loaded_at": int, "last_access": int, "ref_bit": int, "dirty": bool}, None, ...]
        self.memory = [None] * memory_blocks
        
        # 统计数据
        self.miss_count = 0
        self.total_count = 0
        self.write_back_count = 0
        
        # 辅助变量
        self.load_counter = 0   # FIFO
        self.clock_hand = 0     # LINUX
        
    def process(self, page_id, op_type, current_time, future_pages):
        """
        处理一次内存访问
        op_type: 'R' (Read) or 'W' (Write)
        """
        self.total_count += 1
        status = "Hit"
        swapped_out = None
        is_write_back = False
        
        # 1. 检查命中
        hit_idx = -1
        for i, frame in enumerate(self.memory):
            if frame is not None and frame['page'] == page_id:
                hit_idx = i
                break
        
        if hit_idx != -1:
            # === Hit ===
            self.memory[hit_idx]['last_access'] = current_time
            if self.name == "LINUX":
                self.memory[hit_idx]['ref_bit'] = 1
            
            # 写操作标记 Dirty
            if op_type == 'W':
                self.memory[hit_idx]['dirty'] = True
        else:
            # === Miss ===
            status = "Miss"
            self.miss_count += 1
            self.load_counter += 1
            
            new_frame = {
                "page": page_id,
                "loaded_at": self.load_counter,
                "last_access": current_time,
                "ref_bit": 1,
                "dirty": (op_type == 'W')
            }
            
            # 找空位
            empty_idx = -1
            for i in range(self.memory_blocks):
                if self.memory[i] is None:
                    empty_idx = i
                    break
            
            if empty_idx != -1:
                self.memory[empty_idx] = new_frame
                if self.name == "LINUX":
                    self.clock_hand = (empty_idx + 1) % self.memory_blocks
            else:
                # 置换
                victim_idx = self._get_victim(future_pages)
                victim_frame = self.memory[victim_idx]
                swapped_out = victim_frame['page']
                
                # Check Dirty Bit (写回检查)
                if victim_frame.get('dirty', False):
                    self.write_back_count += 1
                    is_write_back = True
                
                self.memory[victim_idx] = new_frame

        return {
            "status": status,
            "swapped": swapped_out,
            "is_write_back": is_write_back
        }

    def _get_victim(self, future_pages):
        valid_frames = [f for f in self.memory if f is not None]
        if not valid_frames: return 0

        if self.name == "FIFO":
            victim = min(valid_frames, key=lambda x: x['loaded_at'])
            return self.memory.index(victim)
        elif self.name == "LRU":
            victim = min(valid_frames, key=lambda x: x['last_access'])
            return self.memory.index(victim)
        elif self.name == "OPT":
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
        elif self.name == "LINUX":
            # Clock 算法
            for _ in range(self.memory_blocks * 2 + 1):
                frame = self.memory[self.clock_hand]
                if frame['ref_bit'] == 1:
                    frame['ref_bit'] = 0
                    self.clock_hand = (self.clock_hand + 1) % self.memory_blocks
                else:
                    victim_idx = self.clock_hand
                    self.clock_hand = (self.clock_hand + 1) % self.memory_blocks
                    return victim_idx
            return self.clock_hand
        return 0

    def predict_next_victim(self, future_pages):
        """预测下一个受害者（仅用于UI高亮）"""
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


class PageManager:
    """总控制器：管理指令流和多算法状态"""
    def __init__(self, total_instructions=320, total_pages=32, memory_blocks=4):
        self.total_instructions = total_instructions
        self.memory_blocks = memory_blocks
        self.total_pages = total_pages
        
        self.instructions = self._generate_instructions()
        
        self.algos = {
            "FIFO": AlgoState("FIFO", memory_blocks),
            "LRU": AlgoState("LRU", memory_blocks),
            "OPT": AlgoState("OPT", memory_blocks),
            "LINUX": AlgoState("LINUX", memory_blocks)
        }
        
        self.current_inst_idx = 0
        self.current_time = 0
        self.view_algo_name = "FIFO"
        self.mode = "NORMAL"

    def _generate_instructions(self):
        """生成指令序列：70%冷数据 + 30%热点数据"""
        insts = []
        hot_page_range = (0, 39) 
        cold_inst_ptr = 40
        for _ in range(self.total_instructions):
            op_type = 'W' if random.random() < 0.3 else 'R'
            rand_val = random.random()
            if rand_val < 0.7:  
                insts.append((cold_inst_ptr, op_type))
                cold_inst_ptr += 1
                if cold_inst_ptr >= self.total_instructions:
                    cold_inst_ptr = 40
            else:
                hot_inst = random.randint(hot_page_range[0], hot_page_range[1])
                insts.append((hot_inst, op_type))
        return insts[:self.total_instructions]

    def load_belady_sequence(self):
        """加载 Belady 异常经典序列"""
        self.mode = "BELADY"
        pages = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
        self.instructions = [(p * 10, 'R') for p in pages] 
        self.current_inst_idx = 0
        self.reset_algos()

    def get_page_id(self, instruction_addr):
        return instruction_addr // 10

    def step(self):
        """执行单步模拟"""
        if self.current_inst_idx >= len(self.instructions):
            return None

        addr, op_type = self.instructions[self.current_inst_idx]
        page_id = self.get_page_id(addr)
        self.current_time += 1
        
        future_tuples = self.instructions[self.current_inst_idx+1:]
        future_pages = [self.get_page_id(x[0]) for x in future_tuples]
        
        step_results = {}
        for name, algo in self.algos.items():
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
        
        view_algo = self.algos[self.view_algo_name]
        mem_view = []
        next_victim = view_algo.predict_next_victim(future_pages)
        
        for i, f in enumerate(view_algo.memory):
            if f is None:
                mem_view.append(None)
            else:
                meta = ""
                if self.view_algo_name == "FIFO": meta = f"SEQ:{f['loaded_at']}"
                elif self.view_algo_name == "LRU": meta = f"IDLE:{self.current_time - f['last_access']}"
                elif self.view_algo_name == "LINUX": meta = f"REF:{f['ref_bit']}"
                elif self.view_algo_name == "OPT": meta = "OPT"
                
                if f.get('dirty'):
                    meta = "DIRTY"
                
                is_hand = (self.view_algo_name == "LINUX" and i == view_algo.clock_hand)
                mem_view.append({
                    "page": f['page'], 
                    "meta": meta, 
                    "is_hand": is_hand,
                    "is_dirty": f.get('dirty', False)
                })

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
        self.instructions = self._generate_instructions()
        self.reset_algos()
        
    def reset_algos(self):
        for algo in self.algos.values():
            algo.memory = [None] * self.memory_blocks
            algo.miss_count = 0
            algo.total_count = 0
            algo.write_back_count = 0
            algo.load_counter = 0
            algo.clock_hand = 0