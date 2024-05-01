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
import ast
import logging
import os
from typing import Dict, Optional, Set, List

from pycg import utils
from pycg.machinery.classes import ClassManager
from pycg.machinery.imports import ImportManager
from pycg.machinery.definitions import Definition, DefinitionManager
from pycg.machinery.scopes import ScopeManager
from pycg.machinery.modules import ModuleManager

node_decoder_counter = 0

logger = logging.getLogger(__name__)


class ProcessingBase(ast.NodeVisitor):
    def_manager: DefinitionManager
    class_manager: ClassManager
    scope_manager: ScopeManager
    import_manager: ImportManager
    module_manager: ModuleManager
    closured: Dict[str, Set[str]]

    def __init__(self, filename: str, modname: str, modules_analyzed: Set[str]) -> None:
        logger.debug(
            "In ProcessingBase.__init__: filename: %s; mod_name: %s; "
            " analyzed modules: %s"
            %(filename, modname, str(modules_analyzed))
        )

        self.possible_fuzz_entrypoints = []

        self.modname = modname

        self.modules_analyzed = modules_analyzed
        self.modules_analyzed.add(self.modname)

        self.filename = os.path.abspath(filename)

        print("Opening: %s"%(filename))
        if os.path.basename(filename).endswith(".so"):
            self.contents = ""
        else:
            ff = open(filename, "rt")
            try:
                self.contents = ff.read()
            except:
                self.contents = ""

        self.name_stack: List[str] = []
        self.method_stack: List[str] = []
        self.last_called_names = None
        logger.debug("Exit ProcessingBase.__init__")

    def get_modules_analyzed(self) -> Set[str]:
        logger.debug("Called ProcessingBase.get_modules_analyzed")
        return self.modules_analyzed

    def merge_modules_analyzed(self, analyzed: Set[str]) -> None:
        logger.debug("In ProcessingBase.merge_modules_analyzed")
        self.modules_analyzed.update(analyzed)
        logger.debug("Exit ProcessingBase.merge_modules_analyzed")

    @property
    def current_ns(self) -> str:
        #logger.debug("Called ProcessingBase.current_ns")
        return ".".join(self.name_stack)

    @property
    def current_method(self) -> str:
        #logger.debug("Called ProcessingBase.current_method")
        return ".".join(self.method_stack)

    def visit_Module(self, node: ast.Module) -> None:
        logger.debug("In ProcessingBase.visit_Module")
        self.name_stack.append(self.modname)
        self.method_stack.append(self.modname)
        self.scope_manager.get_scope(self.modname).reset_counters()
        self.generic_visit(node)
        self.method_stack.pop()
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_Module")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        logger.debug("In ProcessingBase.visit_FunctionDef")
        self.name_stack.append(node.name)
        self.method_stack.append(node.name)
        if self.scope_manager.get_scope(self.current_ns):
            self.scope_manager.get_scope(self.current_ns).reset_counters()
            for stmt in node.body:
                self.visit(stmt)
        self.method_stack.pop()
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_FunctionDef")

    def visit_Lambda(self, node: ast.Lambda, lambda_name=None):
        # logger.debug("In ProcessingBase.visit_Lambda")
        lambda_ns = utils.join_ns(self.current_ns, lambda_name)
        if not self.scope_manager.get_scope(lambda_ns):
            self.scope_manager.create_scope(lambda_ns,
                    self.scope_manager.get_scope(self.current_ns))
        self.name_stack.append(lambda_name)
        self.method_stack.append(lambda_name)
        self.visit(node.body)
        self.method_stack.pop()
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_Lambda")

    def visit_For(self, node: ast.For):
        logger.debug("In ProcessingBase.visit_For")
        for item in node.body:
            self.visit(item)
        logger.debug("Exit ProcessingBase.visit_For")

    def visit_Dict(self, node: ast.Dict):
        logger.debug("In ProcessingBase.visit_Dict")
        counter = self.scope_manager.get_scope(self.current_ns).inc_dict_counter()
        dict_name = utils.get_dict_name(counter)

        sc = self.scope_manager.get_scope(utils.join_ns(self.current_ns, dict_name))
        if not sc:
            logger.debug("Exit ProcessingBase.visit_Dict: No scope definition")
            return
        self.name_stack.append(dict_name)
        sc.reset_counters()
        for key, val in zip(node.keys, node.values):
            if key:
                self.visit(key)
            if val:
                self.visit(val)
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_Dict")

    def visit_List(self, node: ast.List):
        logger.debug("In ProcessingBase.visit_List")
        counter = self.scope_manager.get_scope(self.current_ns).inc_list_counter()
        list_name = utils.get_list_name(counter)

        sc = self.scope_manager.get_scope(utils.join_ns(self.current_ns, list_name))
        if not sc:
            logger.debug("Exit ProcessingBase.visit_List: No scope definition")
            return
        self.name_stack.append(list_name)
        sc.reset_counters()
        for elt in node.elts:
            self.visit(elt)
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_List")

    def visit_BinOp(self, node):
        logger.debug("In ProcessingBase.visit_BinOp")
        self.visit(node.left)
        self.visit(node.right)
        logger.debug("Exit ProcessingBase.visit_BinOp")

    def visit_ClassDef(self, node: ast.ClassDef):
        logger.debug("In ProcessingBase.visit_ClassDef")
        self.name_stack.append(node.name)
        self.method_stack.append(node.name)
        if self.scope_manager.get_scope(self.current_ns) != None:
            self.scope_manager.get_scope(self.current_ns).reset_counters()
            for stmt in node.body:
                self.visit(stmt)
        self.method_stack.pop()
        self.name_stack.pop()
        logger.debug("Exit ProcessingBase.visit_ClassDef")

    def visit_Tuple(self, node):
        logger.debug("In ProcessingBase.visit_Tuple")
        for elt in node.elts:
            self.visit(elt)
        logger.debug("Exit ProcessingBase.visit_Tuple")

    def _handle_assign(self, targetns, decoded):
        logger.debug("In ProcessingBase._handle_assign")
        defi = self.def_manager.get(targetns)
        if not defi:
            defi = self.def_manager.create(targetns, utils.constants.NAME_DEF)

        # check if decoded is iterable
        try:
            iter(decoded)
        except TypeError:
            logger.debug("Exit ProcessingBase._handle_assign: No definition found")
            return defi

        for d in decoded:
            if isinstance(d, Definition):
                defi.get_name_pointer().add(d.get_ns())
            else:
                defi.get_lit_pointer().add(d)
        logger.debug("Exit ProcessingBase._handle_assign")
        return defi

    def _visit_return(self, node):
        logger.debug("In ProcessingBase._visit_return")
        if not node or not node.value:
            return

        self.visit(node.value)

        return_ns = utils.join_ns(self.current_ns, utils.constants.RETURN_NAME)
        self._handle_assign(return_ns, self.decode_node(node.value))
        logger.debug("Exit ProcessingBase._visit_return")

    def _get_target_ns(self, target):
        logger.debug("In ProcessingBase._get_target_ns")
        if isinstance(target, ast.Name):
            logger.debug("Exit ProcessingBase._get_target_ns: Node type: Name")
            return [utils.join_ns(self.current_ns, target.id)]
        if isinstance(target, ast.Attribute):
            bases = self._retrieve_base_names(target)
            res = []
            for base in bases:
                res.append(utils.join_ns(base, target.attr))
            logger.debug("Exit ProcessingBase._get_target_ns: Node type: Attribute")
            return res
        if isinstance(target, ast.Subscript):
            logger.debug("Exit ProcessingBase._get_target_ns: Node type: Subscript")
            return self.retrieve_subscript_names(target)
        logger.debug("Exit ProcessingBase._get_target_ns: Invalid node type")
        return []

    def _visit_assign(self, value, targets):
        logger.debug("In ProcessingBase._visit_assign")
        self.visit(value)

        decoded = self.decode_node(value)

        def do_assign(decoded, target):
            logger.debug("In ProcessingBase._visit_assign.do_assign: Target: %s" % target)
            self.visit(target)
            if isinstance(target, ast.Tuple):
                for pos, elt in enumerate(target.elts):
                    if not isinstance(decoded, Definition) and pos < len(decoded):
                        do_assign(decoded[pos], elt)
            else:
                targetns = self._get_target_ns(target)
                for tns in targetns:
                    if not tns:
                        continue
                    defi = self._handle_assign(tns, decoded)
                    splitted = tns.split(".")
                    self.scope_manager.handle_assign(".".join(splitted[:-1]), splitted[-1], defi)
            logger.debug("Exit ProcessingBase._visit_assign.do_assign")

        for target in targets:
            do_assign(decoded, target)
        logger.debug("Exit ProcessingBase._visit_assign")

    def decode_node(self, node) -> List[Definition]:
        global node_decoder_counter
        #logger.debug("Node counter: %d"%(node_decoder_counter))
        node_decoder_counter += 1
        #logger.debug("In ProcessingBase.decode_node")
        if isinstance(node, ast.Name):
            #logger.debug("DEC-1")
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Name")

            node_decoder_counter -= 1
            return [self.scope_manager.get_def(self.current_ns, node.id)]
        elif isinstance(node, ast.Call):
            #logger.debug("DEC-2")
            decoded = self.decode_node(node.func)
            return_defs: List[Definition] = []
            for called_def in decoded:
                if not isinstance(called_def, Definition):
                    continue

                return_ns = utils.constants.INVALID_NAME
                if called_def.is_function_def():
                    return_ns = utils.join_ns(called_def.get_ns(), utils.constants.RETURN_NAME)
                elif called_def.is_class_def():
                    return_ns = called_def.get_ns()
                elif called_def.is_ext_def():
                    return_ns_set = called_def.get_name_pointer().values
                    if return_ns_set:
                        return_ns = next(iter(return_ns_set))
                defi = self.def_manager.get(return_ns)
                if defi:
                    return_defs.append(defi)

            #logger.debug("Exit ProcessingBase.decode_node: Node type: Call")
            node_decoder_counter -= 1
            return return_defs
        elif isinstance(node, ast.Lambda):
            #logger.debug("DEC-3")
            lambda_counter = self.scope_manager.get_scope(self.current_ns).get_lambda_counter()
            lambda_name = utils.get_lambda_name(lambda_counter)
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Lambda")
            node_decoder_counter -= 1
            return [self.scope_manager.get_def(self.current_ns, lambda_name)]
        elif isinstance(node, ast.Tuple):
            #logger.debug("DEC-4")
            decoded = []
            for elt in node.elts:
                decoded.append(self.decode_node(elt))
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Tuple")
            node_decoder_counter -= 1
            return decoded
        elif isinstance(node, ast.BinOp):
            #logger.debug("DEC-5")
            decoded_left = self.decode_node(node.left)
            decoded_right = self.decode_node(node.right)
            # return the non definition types if we're talking about a binop
            # since we only care about the type of the return (num, str, etc)
            if not isinstance(decoded_left, Definition):
                #logger.debug("Exit ProcessingBase.decode_node: Node type: BinOp->Left")
                node_decoder_counter -= 1
                return decoded_left
            if not isinstance(decoded_right, Definition):
                #logger.debug("Exit ProcessingBase.decode_node: Node type: BinOp->Right")
                node_decoder_counter -= 1
                return decoded_right
        elif isinstance(node, ast.Attribute):
            #logger.debug("DEC-6")
            names = self._retrieve_attribute_names(node)
            defis = []
            for name in names:
                defi = self.def_manager.get(name)
                if defi:
                    defis.append(defi)
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Attribute")
            node_decoder_counter -= 1
            return defis
        elif isinstance(node, ast.Num):
            #logger.debug("DEC-7")
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Num")
            node_decoder_counter -= 1
            return [node.n]
        elif isinstance(node, ast.Str):
            #logger.debug("DEC-8")
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Str")
            node_decoder_counter -= 1
            return [node.s]
        elif self._is_literal(node):
            #logger.debug("DEC-9")
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Literal Node")
            node_decoder_counter -= 1
            return [node]
        elif isinstance(node, ast.Dict):
            #logger.debug("DEC-10")
            dict_counter = self.scope_manager.get_scope(self.current_ns).get_dict_counter()
            dict_name = utils.get_dict_name(dict_counter)
            scope_def = self.scope_manager.get_def(self.current_ns, dict_name)
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Dict")
            node_decoder_counter -= 1
            return [self.scope_manager.get_def(self.current_ns, dict_name)]
        elif isinstance(node, ast.List):
            #logger.debug("DEC-11")
            list_counter = self.scope_manager.get_scope(self.current_ns).get_list_counter()
            list_name = utils.get_list_name(list_counter)
            scope_def = self.scope_manager.get_def(self.current_ns, list_name)
            #logger.debug("Exit ProcessingBase.decode_node: Node type: List")
            node_decoder_counter -= 1
            return [self.scope_manager.get_def(self.current_ns, list_name)]
        elif isinstance(node, ast.Subscript):
            #logger.debug("DEC-12")
            names = self.retrieve_subscript_names(node)
            defis = []
            for name in names:
                defi = self.def_manager.get(name)
                if defi:
                    defis.append(defi)
            #logger.debug("Exit ProcessingBase.decode_node: Node type: Subscript")
            node_decoder_counter -= 1
            return defis

        #logger.debug("Exit ProcessingBase.decode_node: Invalid node type")
        node_decoder_counter -= 1
        return []

    def _is_literal(self, item) -> bool:
        logger.debug("Called ProcessingBase._is_literal")
        return isinstance(item, int) or isinstance(item, str) or isinstance(item, float)

    def _retrieve_base_names(self, node):
        #logger.debug("In ProcessingBase._retrieve_base_names")
        if not isinstance(node, ast.Attribute):
            raise Exception("The node is not an attribute")

        if not getattr(self, "closured", None):
            #logger.debug("Exit ProcessingBase._retrieve_base_names: Not closure")
            return set()

        decoded = self.decode_node(node.value)
        if not decoded:
            #logger.debug("Exit ProcessingBase._retrieve_base_names: Fail to decode node value")
            return set()

        names = set()
        for name in decoded:
            if not name or not isinstance(name, Definition):
                continue

            for base in self.closured.get(name.get_ns(), []):
                cls = self.class_manager.get(base)
                if not cls:
                    continue

                for item in cls.get_mro():
                    names.add(item)
        #logger.debug("Exit ProcessingBase._retrieve_base_names")
        return names


    def _retrieve_parent_names(self, node):
        #logger.debug("In ProcessingBase._retrieve_parent_names")
        if not isinstance(node, ast.Attribute):
            raise Exception("The node is not an attribute")
        decoded = self.decode_node(node.value)
        if not decoded:
            #logger.debug("Exit ProcessingBase._retrieve_parent_names: Fail to decode node value")
            return set()

        names = set()
        for parent in decoded:
            if not parent or not isinstance(parent, Definition):
                continue
            if getattr(self, "closured", None) and self.closured.get(parent.get_ns(), None):
                names.update(self.closured.get(parent.get_ns()))
            else:
                names.add(parent.get_ns())
        #logger.debug("Exit ProcessingBase._retrieve_parent_names")
        return names

    def _retrieve_attribute_names(self, node):
        #logger.debug("In ProcessingBase._retrieve_attribute_names")
        if not getattr(self, "closured", None):
            #logger.debug("Exit ProcessingBase._retrieve_attribute_names: Not closure")
            return set()
        #logger.debug("D-1")
        parent_names = self._retrieve_parent_names(node)
        names = set()
        for parent_name in parent_names:
            #logger.debug("D-2")
            for name in self.closured.get(parent_name, []):
                #logger.debug("D-3")
                defi = self.def_manager.get(name)
                if not defi:
                    continue
                #logger.debug("D-3.1")
                if defi.is_class_def():
                    #logger.debug("D-3.1-1")
                    cls_names = self.find_cls_fun_ns(defi.get_ns(), node.attr)
                    if cls_names:
                        #logger.debug("D-3.1-2")
                        names.update(cls_names)
                #logger.debug("D-3.2")
                if defi.is_function_def() or defi.is_module_def():
                    #logger.debug("D-3.3")
                    names.add(utils.join_ns(name, node.attr))
                #logger.debug("D-3.4")
                if defi.is_ext_def():
                    #logger.debug("D-3.5")
                    # HACK: extenral attributes can lead to infinite loops
                    # Identify them here
                    if node.attr in name:
                        continue
                    #logger.debug("D-3.6")
                    ext_name = utils.join_ns(name, node.attr)
                    if not self.def_manager.get(ext_name):
                        #logger.debug("D-3.7")
                        self.def_manager.create(ext_name, utils.constants.EXT_DEF)
                    #logger.debug("D-3.8")
                    names.add(ext_name)

        #logger.debug("D-10")
        #logger.debug("Exit ProcessingBase._retrieve_attribute_names")
        return names

    def iterate_call_args(self, defi: Definition, node):
        #logger.debug("In ProcessingBase.iterate_call_args")
        for pos, arg in enumerate(node.args):
            self.visit(arg)
            decoded = self.decode_node(arg)
            if defi.is_function_def():
                pos_arg_names = defi.get_name_pointer().get_pos_arg(pos)
                # if arguments for this position exist update their namespace
                if not pos_arg_names:
                    continue
                for name in pos_arg_names:
                    arg_def = self.def_manager.get(name)
                    if not arg_def:
                        continue
                    for d in decoded:
                        if isinstance(d, Definition):
                            arg_def.get_name_pointer().add(d.get_ns())
                        else:
                            arg_def.get_lit_pointer().add(d)
            else:
                for d in decoded:
                    if isinstance(d, Definition):
                        defi.get_name_pointer().add_pos_arg(pos, None, d.get_ns())
                    else:
                        defi.get_name_pointer().add_pos_lit_arg(pos, None, d)

        for keyword in node.keywords:
            self.visit(keyword.value)
            decoded = self.decode_node(keyword.value)
            if defi.is_function_def():
                arg_names = defi.get_name_pointer().get_arg(keyword.arg)
                if not arg_names:
                    continue
                for name in arg_names:
                    arg_def = self.def_manager.get(name)
                    if not arg_def:
                        continue
                    for d in decoded:
                        if isinstance(d, Definition):
                            arg_def.get_name_pointer().add(d.get_ns())
                        else:
                            arg_def.get_lit_pointer().add(d)
            else:
                for d in decoded:
                    if isinstance(d, Definition):
                        defi.get_name_pointer().add_arg(keyword.arg, d.get_ns())
                    else:
                        defi.get_name_pointer().add_lit_arg(keyword.arg, d)
        #logger.debug("Exit ProcessingBase.loiterate_call_args")

    def retrieve_subscript_names(self, node) -> Set[str]:
        # logger.debug("In ProcessingBase.retrieve_subscript_names")
        if not isinstance(node, ast.Subscript):
            raise Exception("The node is not an subcript")

        if not getattr(self, "closured", None):
            #logger.debug("Exit ProcessingBase.retrieve_subscript_names: Not Closure")
            return set()

        if getattr(node.slice, "value", None) and self._is_literal(node.slice.value):
            sl_names = [node.slice.value]
        else:
            sl_names = self.decode_node(node.slice)

        val_names = self.decode_node(node.value)

        decoded_vals: Set[str] = set()
        keys = set()
        full_names = set()
        # get all names associated with this variable name
        for n in val_names:
            if n and isinstance(n, Definition) and n.get_ns() in self.closured:
                decoded_vals |= self.closured.get(n.get_ns())
        for s in sl_names:
            if isinstance(s, Definition) and s.get_ns() in self.closured:
                # we care about the literals pointed by the name
                # not the namespaces, so retrieve the literals pointed
                for name in self.closured.get(s.get_ns()):
                    defi = self.def_manager.get(name)
                    if not defi:
                        continue
                    keys |= defi.get_lit_pointer().values
            elif isinstance(s, str):
                keys.add(s)
            elif isinstance(s, int):
                keys.add(utils.get_int_name(s))

        for d in decoded_vals:
            for key in keys:
                # check for existence of var name and key combination
                str_key = str(key)
                if isinstance(key, int):
                    str_key = utils.get_int_name(key)
                full_ns = utils.join_ns(d, str_key)
                full_names.add(full_ns)

        #logger.debug("Exit ProcessingBase.retrieve_subscript_names")
        return full_names

    def retrieve_call_names(self, node) -> Optional[Set[str]]:
        # logger.debug("In ProcessingBase.retrieve_call_names")
        names: Set[str] = set()
        if isinstance(node.func, ast.Name):
            defi = self.scope_manager.get_def(self.current_ns, node.func.id)
            if defi:
                names = self.closured.get(defi.get_ns(), set())
        elif isinstance(node.func, ast.Call) and self.last_called_names:
            for name in self.last_called_names:
                return_ns = utils.join_ns(name, utils.constants.RETURN_NAME)
                returns = self.closured.get(return_ns)
                if not returns:
                    continue
                for ret in returns:
                    defi = self.def_manager.get(ret)
                    names.add(defi.get_ns())
        elif isinstance(node.func, ast.Attribute):
            names = self._retrieve_attribute_names(node.func)
        elif isinstance(node.func, ast.Subscript):
            # Calls can be performed only on single indices, not ranges
            full_names = self.retrieve_subscript_names(node.func)
            for n in full_names:
                if n in self.closured:
                    names |= self.closured[n]

        #logger.debug("Exit ProcessingBase.retrieve_call_names")
        return names

    def analyze_submodules(self, cls, *args, **kwargs) -> None:
        #logger.debug("In ProcessingBase.analyze_submodules")
        imports = self.import_manager.get_imports(self.modname)

        for imp in imports:
            self.analyze_submodule(cls, imp, *args, **kwargs)
        #logger.debug("Exit ProcessingBase.analyze_submodules")

    def analyze_submodule(self, cls, imp, *args, **kwargs) -> None:
        #logger.debug("In ProcessingBase.analyze_submodule")
        if imp in self.get_modules_analyzed():
            #logger.debug("Exit ProcessingBase.analyze_submodule: Skip analyzed module: %s" % imp)
            return

        fname = self.import_manager.get_filepath(imp)

        if not fname or not self.import_manager.get_mod_dir() in fname:
            #logger.debug("Exit ProcessingBase.analyze_submodule: Fail to locate module source:  %s" % imp)
            return

        self.import_manager.set_current_mod(imp, fname)

        visitor = cls(fname, imp, *args, **kwargs)
        visitor.analyze()
        self.merge_modules_analyzed(visitor.get_modules_analyzed())

        self.import_manager.set_current_mod(self.modname, self.filename)
        #logger.debug("Exit ProcessingBase.analyze_submodule")

    def find_cls_fun_ns(self, cls_name: str, fn):
        # logger.debug("In ProcessingBase.find_cls_fun_ns")
        cls = self.class_manager.get(cls_name)
        if not cls:
            #logger.debug("Exit ProcessingBase.find_cls_fun_ns: No class manager found")
            return set()

        ext_names = set()
        for item in cls.get_mro():
            ns = utils.join_ns(item, fn)
            names = set()
            if getattr(self, "closured", None) and self.closured.get(ns, None):
                names = self.closured[ns]
            else:
                names.add(ns)

            if self.def_manager.get(ns):
                #logger.debug("Exit ProcessingBase.find_cls_fun_ns: Found from definition manager")
                return names

            parent = self.def_manager.get(item)
            if parent and parent.is_ext_def():
                ext_names.add(ns)

        for name in ext_names:
            self.def_manager.create(name, utils.constants.EXT_DEF)
            self.add_ext_mod_node(name)

        #logger.debug("Exit ProcessingBase.find_cls_fun_ns: Found from external source")
        return ext_names

    def add_ext_mod_node(self, name: str) -> None:
        # logger.debug("In ProcessingBase.add_ext_mod_node")
        ext_modname = name.split(".")[0]
        ext_mod = self.module_manager.get(ext_modname)
        if not ext_mod:
            ext_mod = self.module_manager.create(ext_modname, None, external=True)
            ext_mod.add_method(ext_modname)

        ext_mod.add_method(name)
        #logger.debug("Exit ProcessingBase.add_ext_mod_node")
