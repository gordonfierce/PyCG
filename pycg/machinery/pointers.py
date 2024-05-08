#
# Copyright (c) 2020 Vitalis Salis.
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
import logging
from typing import Dict, Optional, Set, Union

logger = logging.getLogger(__name__)


class Pointer:
    def __init__(self) -> None:
        # logger.debug("In Pointer.__ini__")
        self.values = set()

    def add(self, item: str):
        # logger.debug("In Pointer.add")
        self.values.add(item)

    def add_set(self, s: set):
        # logger.debug("In Pointer.add_set")
        self.values.update(s)

    def get(self):
        # logger.debug("In Pointer.get")
        return self.values

    def merge(self, pointer):
        # logger.debug("In Pointer.merge")
        self.values.update(pointer.values)


class LiteralPointer(Pointer):
    __slots__ = ["values"]
    STR_LIT = "STRING"
    INT_LIT = "INTEGER"
    UNK_LIT = "UNKNOWN"

    # no need to add the actual item
    def add(self, item):
        # logger.debug("In LiteralPointer.add")
        if isinstance(item, str):
            self.values.add(item)
        elif isinstance(item, int):
            self.values.add(item)
        else:
            self.values.add(self.UNK_LIT)


class NamePointer(Pointer):
    __slots__ = ["pos_to_name", "name_to_pos", "args", "values"]
    values: Set[str]

    def __init__(self) -> None:
        # logger.debug("In NamePointer.__init__")
        super().__init__()
        self.pos_to_name: Dict[int, str] = {}
        self.name_to_pos: Dict[str, int] = {}
        self.args: Dict[str, Set[str]] = {}

    def __repr__(self):
        return f"<NamePointer pos_to_name={self.pos_to_name} name_to_pos={self.name_to_pos}, args={self.args}, values={self.values}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NamePointer):
            return NotImplemented
        return (self.pos_to_name == other.pos_to_name and
                self.name_to_pos == other.name_to_pos and
                self.args == other.args and
                self.values == other.values)

    def __hash__(self) -> int:
        # Create a hash based on a tuple of the hashes of the frozen contents of attributes.
        # This is a simple approach and might need to be adjusted for performance considerations.
        return hash((frozenset(self.pos_to_name.items()), frozenset(self.name_to_pos.items()), 
                     frozenset((k, frozenset(v)) for k, v in self.args.items())))

    def _sanitize_pos(self, pos) -> int:
        # logger.debug("In NamePointer._sanitize_pos")
        try:
            int(pos)
        except ValueError:
            raise PointerError("Invalid position for argument")

        return pos

    def get_or_create(self, name: str) -> Set[str]:
        # logger.debug("In NamePointer.get_or_create")
        if not name in self.args:
            self.args[name] = set()
        return self.args[name]

    def add_arg(self, name: str, item: Union[str, Set[str]]) -> None:
        # logger.debug("In NamePointer.add_arg")
        arg = self.get_or_create(name)
        if isinstance(item, str):
            self.args[name].add(item)
        elif isinstance(item, set):
            self.args[name].update(item)
        else:
            raise Exception()

    def add_lit_arg(self, name: str, item) -> None:
        # logger.debug("In NamePointer.add_lit_arg")
        arg = self.get_or_create(name)
        if isinstance(item, str):
            arg.add(LiteralPointer.STR_LIT)
        elif isinstance(item, int):
            arg.add(LiteralPointer.INT_LIT)
        else:
            arg.add(LiteralPointer.UNK_LIT)

    def add_pos_arg(self, pos: int, name: Optional[str], item):
        # logger.debug("In NamePointer.add_pos_arg")
        pos = self._sanitize_pos(pos)
        if not name:
            if self.pos_to_name.get(pos, None):
                name = self.pos_to_name[pos]
            else:
                name = str(pos)
        self.pos_to_name[pos] = name
        self.name_to_pos[name] = pos

        self.add_arg(name, item)

    def add_name_arg(self, name: str, item):
        # logger.debug("In NamePointer.add_name_arg")
        self.add_arg(name, item)

    def add_pos_lit_arg(self, pos: int, name: str, item):
        # logger.debug("In NamePointer.add_pos_lit_arg")
        pos = self._sanitize_pos(pos)
        if not name:
            name = str(pos)
        self.pos_to_name[pos] = name
        self.name_to_pos[name] = pos
        self.add_lit_arg(name, item)

    def get_pos_arg(self, pos: int):
        # logger.debug("In NamePointer.get_pos_arg")

        name = self.pos_to_name.get(pos)
        if name:
            return self.args.get(name)

    def get_arg(self, name):
        # logger.debug("In NamePointer.get_arg")
        return self.args.get(name)

    def get_args(self):
        # logger.debug("In NamePointer.get_args")
        return self.args

    def get_pos_args(self):
        # logger.debug("In NamePointer.get_pos_args")
        args = {}
        for pos, name in self.pos_to_name.items():
            args[pos] = self.args[name]
        return args

    def get_pos_of_name(self, name) -> Optional[int]:
        # logger.debug("In NamePointer.get_pos_of_name")
        if name in self.name_to_pos:
            return self.name_to_pos[name]
        else:
            return None

    def get_pos_names(self) -> Dict[int, str]:
        # logger.debug("In NamePointer.get_pos_names")
        return self.pos_to_name

    def merge(self, pointer) -> None:
        # logger.debug("In NamePointer.merge")
        super().merge(pointer)
        if hasattr(pointer, "get_pos_names"):
            for pos, name in pointer.pos_to_name.items():
                self.pos_to_name[pos] = name
            for name, arg in pointer.args.items():
                self.add_arg(name, arg)


class PointerError(Exception):
    pass
