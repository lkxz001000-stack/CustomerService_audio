"""
YAML 流程配置加载器。

从 flow_config/ 目录加载 .yml 文件，解析为 FlowsList 领域对象。
支持一次加载多个 YAML 文件并合并结果。
"""

import yaml
from typing import Any
from pathlib import Path
from audio_cs.task.flow.flows import FlowsList, FlowSlot, Flow, FlowStep
from audio_cs.task.flow.steps import CollectFlowStep

class FlowLoader:
    """YAML 流程配置加载器：将 YAML 字典解析为强类型的 Flow/FlowStep/FlowSlot 对象。"""

    def load_many_yaml(self, paths: list[str | Path]) -> FlowsList:
        """加载多个 YAML 文件并合并为一个 FlowsList。"""
        flows: list[Flow] = []
        slots: dict[str, FlowSlot] = {}
        for path in paths:
            loaded = self.load_yaml(path)
            flows.extend(loaded.flows)
            slots.update(loaded.slots)
        return FlowsList(flows=flows, slots=slots)

    def load_yaml(self, path: Path) -> FlowsList:
        """加载单个 YAML 文件，返回包含 flows 和 slots 的 FlowsList。"""
        # 1. 读取 YAML 文件为字典
        with open(path, 'r', encoding='utf-8') as f:
            dict_data = yaml.safe_load(f)

        # 2. 先加载 slots（槽位定义）
        loaded_slots: dict[str, FlowSlot] = self.load_slots(dict_data.get('slots', {}))

        # 3. 再加载 flows（流程定义，引用已加载的 slots）
        loaded_flows: list[Flow] = self.load_flows(dict_data.get('flows', {}), loaded_slots)

        return FlowsList(slots=loaded_slots, flows=loaded_flows)

    def load_slots(self, slots: dict[str, Any]) -> dict[str, FlowSlot]:
        """
        加载 YAML 中的槽位定义。

        将 YAML 字典中的每个槽位条目转换为 FlowSlot 对象。

        参数:
            slots: YAML 中 slots 区域的原始字典

        返回:
            dict[str, FlowSlot]: 槽位名到 FlowSlot 对象的映射
        """
        loaded_slots: dict[str, FlowSlot] = {}
        for slot_name, slot_dict in slots.items():
            loaded_slots[slot_name] = FlowSlot(
                name=slot_name,
                type=slot_dict.get('type'),
                label=slot_dict.get('label'),
                description=slot_dict.get('description')
            )
        return loaded_slots

    def load_flows(self, flows: dict[str, Any], loaded_slots: dict[str, FlowSlot]) -> list[Flow]:
        """
        加载 YAML 中的流程定义。

        解析每个流程的步骤列表（通过 FlowStep.from_dict 工厂方法创建步骤对象），
        并关联该流程使用的槽位。

        参数:
            flows: YAML 中 flows 区域的原始字典
            loaded_slots: 已加载的全部槽位定义

        返回:
            list[Flow]: Flow 对象列表
        """
        loaded_flows: list[Flow] = []
        for flow_id, flow_dict in flows.items():
            # 每个步骤字典通过工厂方法 FlowStep.from_dict 转换为对应的步骤子类
            steps: list[FlowStep] = [FlowStep.from_dict(step_dict) for step_dict in flow_dict.get('steps', [])]
            loaded_flows.append(
                Flow(
                    flow_id=flow_id,
                    flow_name=flow_dict.get('name'),
                    description=flow_dict.get('description'),
                    steps=steps,
                    slots=self._load_flow_slot(steps, loaded_slots)
                )
            )
        return loaded_flows

    def _load_flow_slot(self, steps: list[FlowStep], loaded_slots: dict[str, FlowSlot]) -> dict[str, FlowSlot]:
        """
        从流程步骤中提取该流程使用的槽位定义。

        遍历所有步骤，筛选出 CollectFlowStep（信息收集步骤），
        将其 slot_name 与全局槽位定义关联。

        参数:
            steps: 流程步骤列表
            loaded_slots: 全局槽位定义字典

        返回:
            dict[str, FlowSlot]: 该流程关联的槽位映射
        """
        seen = set()
        flow_slots: dict[str, FlowSlot] = {}
        for step in steps:
            # 只处理信息收集步骤
            if not isinstance(step, CollectFlowStep):
                continue
            # 获取槽位名称
            flow_slot_name = step.slot_name
            # 从全局槽位定义中查找匹配项
            slot_definition = loaded_slots.get(flow_slot_name)
            if slot_definition is not None:
                flow_slots[flow_slot_name] = slot_definition
        return flow_slots


if __name__ == '__main__':
    yaml_path = Path(__file__).resolve().parents[2] / "flow_config" / "system_flows.yml"
    flow_loader = FlowLoader()
    flow_loader.load_yaml(path=yaml_path)
