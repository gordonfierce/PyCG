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
class ClassManager:
    def __init__(self):
        self.names = {}

    def get(self, name):
        if name in self.names:
            return self.names[name]

    def create(self, name, module):
        if not name in self.names:
            cls = ClassNode(name, module)
            self.names[name] = cls
        return self.names[name]

    def get_classes(self):
        return self.names

class ClassNode:
    def __init__(self, ns, module):
        self.ns = ns
        self.module = module
        self.mro = [ns]

    def add_parent(self, parent):
        print("C-A-1")
        if isinstance(parent, str):
            print("C-A-2")
            self.mro.append(parent)
        elif isinstance(parent, list):
            print("C-A-3")
            if self.mro != parent:
                for item in parent:
                    print("C-A-4: %d"%(len(parent)))
                    if self.mro == parent:
                        print("C-A-4.1")
                    else:
                        print("C-A-4.2")
                    self.mro.append(item)
                    print("C-A-5")
        print("C-A-6")
        self.fix_mro()
        print("C-A-7")

    def fix_mro(self):
        new_mro = []
        print("C-M-1")
        for idx, item in enumerate(self.mro):
            print("C-M-2")
            if self.mro[idx+1:].count(item) > 0:
                print("C-M-2.1")
                continue
            print("C-M-3")
            new_mro.append(item)
            print("C-M-4")
        print("C-M-5")
        self.mro = new_mro
        print("C-M-6")

    def get_mro(self):
        return self.mro

    def get_module(self):
        return self.module

    def compute_mro(self):
        res = []
        self.mro.reverse()
        for parent in self.mro:
            if not parent in res:
                res.append(parent)

        res.reverse()
        self.mro = res

    def clear_mro(self):
        self.mro = [self.ns]
