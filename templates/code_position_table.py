#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
码位表解析器模块

解析lgxtq.zl文件，包含两个部分：
- [objects]: 对象索引表，用于SDCI帧设备状态解析，索引从0开始
- [zlobjects]: SDI Buffer对象位置信息表，用于字节索引映射
"""

import re
from typing import Dict, Optional

from .device_types import DeviceInfo, DeviceType


class CodePositionTable:
    """码位表解析器"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.devices: Dict[int, DeviceInfo] = {}  # 以字节索引为键 (zlobjects)
        self.devices_by_object_index: Dict[
            int, DeviceInfo
        ] = {}  # 以object索引为键 (objects)
        self.devices_by_name: Dict[str, DeviceInfo] = {}  # 以设备名称为键
        self.objects: Dict[str, int] = {}  # objects表: 名称->索引
        self._parse()

    def _determine_device_type(self, name: str) -> DeviceType:
        """根据设备名称确定设备类型"""
        # 纯数字 - 道岔区段
        if name.isdigit():
            return DeviceType.SWITCH_SECTION
        # D开头数字结尾 - 信号机
        elif re.match(r"^D\d+$", name):
            return DeviceType.SIGNAL
        # 其他 - 无岔区段
        else:
            return DeviceType.TRACK_SECTION

    def _parse(self):
        """解析码位表文件"""
        with open(self.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析[objects]部分
        objects_match = re.search(r"\[objects\](.*?)\[end\]", content, re.DOTALL)
        if objects_match:
            objects_section = objects_match.group(1)
            for line in objects_section.strip().split("\n"):
                line = line.strip()
                if line.startswith("#,"):
                    parts = line.split(",")
                    if len(parts) >= 3:
                        name = parts[1].strip()
                        index = int(parts[2].strip())
                        self.objects[name] = index

        # 解析[zlobjects]部分
        zlobjects_match = re.search(r"\[zlobjects\](.*?)\[end\]", content, re.DOTALL)
        if zlobjects_match:
            zlobjects_section = zlobjects_match.group(1)
            for line in zlobjects_section.strip().split("\n"):
                line = line.strip()
                if line.startswith("#,"):
                    parts = line.split(",")
                    if len(parts) >= 4:
                        name = parts[1].strip()
                        byte_index = int(parts[2].strip())
                        bit_offset = int(parts[3].strip())

                        device_type = self._determine_device_type(name)
                        object_index = self.objects.get(name, -1)

                        device = DeviceInfo(
                            name=name,
                            device_type=device_type,
                            object_index=object_index,
                            byte_index=byte_index,
                            bit_offset=bit_offset,
                        )

                        self.devices[byte_index] = device
                        self.devices_by_name[name] = device
                        # 同时建立object索引映射（用于SDCI帧解析）
                        if object_index >= 0:
                            self.devices_by_object_index[object_index] = device

    def get_device_by_byte_index(self, byte_index: int) -> Optional[DeviceInfo]:
        """根据字节索引获取设备信息 (zlobjects表)"""
        return self.devices.get(byte_index)

    def get_device_by_object_index(self, object_index: int) -> Optional[DeviceInfo]:
        """根据object索引获取设备信息 (objects表)"""
        return self.devices_by_object_index.get(object_index)

    def get_device_by_name(self, name: str) -> Optional[DeviceInfo]:
        """根据设备名称获取设备信息"""
        return self.devices_by_name.get(name)
