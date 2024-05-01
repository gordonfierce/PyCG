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
from typing import Optional, Set

from pycg import utils
from pycg.machinery.classes import ClassManager
from pycg.machinery.definitions import Definition, DefinitionManager
from pycg.machinery.imports import ImportManager
from pycg.machinery.scopes import ScopeManager
from pycg.machinery.modules import ModuleManager
from pycg.processing.base import ProcessingBase

logger = logging.getLogger(__name__)


class PostProcessor(ProcessingBase):
    def __init__(
        self,
        input_file: str,
        modname: str,
        import_manager: ImportManager,
        scope_manager: ScopeManager,
        def_manager: DefinitionManager,
        class_manager: ClassManager,
        module_manager: ModuleManager,
        modules_analyzed: Set[str],
    ) -> None:
        logger.debug(
            f"In PreProcessor.__init__: mod_name: {modname}; analyzed_modules: {str(modules_analyzed)}"
        )
        super().__init__(input_file, modname, modules_analyzed)
        self.import_manager = import_manager
        self.scope_manager = scope_manager
        self.def_manager: DefinitionManager = def_manager
        self.class_manager: ClassManager = class_manager
        self.module_manager = module_manager
        self.closured = self.def_manager.transitive_closure()
        logger.debug("Exit PreProcessor.__init__")

    def visit_Lambda(self, node):
        logger.debug("In PreProcessor.visit_Lambda")
        counter = self.scope_manager.get_scope(self.current_ns).inc_lambda_counter()
        lambda_name = utils.get_lambda_name(counter)
        super().visit_Lambda(node, lambda_name)
        logger.debug("Exit PreProcessor.visit_Lambda")

    def visit_Call(self, node: ast.Call):
        # logger.debug("In PreProcessor.visit_Call")
        self.visit(node.func)

        names = self.retrieve_call_names(node)
        if not names:
            return
        for _name in names:
            #logger.debug("- %s"%(_name))
            if "atheris.Setup" in _name:
                logger.info("We found the call to atheris")
                logger.info("%s"%(node.args))
                logger.info("The second argument: %s"%(node.args[1]))
                try:
                  logger.info("Name: %s"%(node.args[1].id))
                  self.possible_fuzz_entrypoints.append(node.args[1].id)
                except:
                  # This error can happen when arguments are passed too atheri.setup which we don't handle
                  pass
                #logger.info("The parsed version: %s"%(ast.dump(node.args)))

        self.last_called_names = names

        for name in names:
            defi = self.def_manager.get(name)
            if not defi:
                continue
            if defi.is_class_def():
                self.update_parent_classes(defi)
                defi = self.def_manager.get(utils.join_ns(defi.fullns, utils.constants.CLS_INIT))
                if not defi:
                    continue
            self.iterate_call_args(defi, node)
        logger.debug("Exit PreProcessor.visit_Call")

    def visit_Assign(self, node):
        logger.debug("In PreProcessor.visit_Assign")
        self._visit_assign(node.value, node.targets)
        logger.debug("Exit PreProcessor.visit_Assign")

    def visit_Return(self, node: ast.Return):
        logger.debug("In PreProcessor.visit_Return")
        self._visit_return(node)
        logger.debug("Exit PreProcessor.visit_Return")

    def visit_Yield(self, node: ast.Yield):
        logger.debug("In PreProcessor.visit_Yield")
        self._visit_return(node)
        logger.debug("Exit PreProcessor.visit_Yield")

    def visit_For(self, node):
        logger.debug("In PreProcessor.visit_For")
        # only handle name targets
        if isinstance(node.target, ast.Name):
            target_def = self.def_manager.get(utils.join_ns(self.current_ns, node.target.id))
            # if the target definition exists
            if target_def:
                iter_decoded = self.decode_node(node.iter)
                # assign the target to the return value
                # of the next function
                for item in iter_decoded:
                    if not isinstance(item, Definition):
                        continue
                    # return value for generators
                    for name in self.closured.get(item.fullns, []):
                        # If there exists a next method on the iterable
                        # and if yes, add a pointer to it
                        next_defi = self.def_manager.get(utils.join_ns(name,
                            utils.constants.NEXT_METHOD, utils.constants.RETURN_NAME))
                        if next_defi:
                            for name in self.closured.get(next_defi.fullns, []):
                                target_def.name_pointer.add(name)
                        else: # otherwise, add a pointer to the name (e.g. a yield)
                            target_def.name_pointer.add(name)

        super().visit_For(node)
        logger.debug("Exit PreProcessor.visit_For")

    def visit_AsyncFunctionDef(self, node):
        logger.debug("In PreProcessor.visit_AsyncFunctionDef")
        self.visit_FunctionDef(node)
        logger.debug("Exit PreProcessor.visit_AsyncFunctionDef")

    def visit_FunctionDef(self, node):
        logger.debug("In PreProcessor.visit_FunctionDef")
        # here we iterate decorators
        if node.decorator_list:
            fn_def = self.def_manager.get(utils.join_ns(self.current_ns, node.name))
            reversed_decorators = list(reversed(node.decorator_list))

            # add to the name pointer of the function definition
            # the return value of the first decorator
            # since, now the function is a namespace to that point
            if hasattr(fn_def, "decorator_names") and reversed_decorators:
                last_decoded = self.decode_node(reversed_decorators[-1])
                for d in last_decoded:
                    if not isinstance(d, Definition):
                        continue
                    fn_def.decorator_names.add(utils.join_ns(d.fullns, utils.constants.RETURN_NAME))

            previous_names = self.closured.get(fn_def.fullns, set())
            for decorator in reversed_decorators:
                # assign the previous_def as the first parameter of the decorator
                decoded = self.decode_node(decorator)
                new_previous_names = set()
                for d in decoded:
                    if not isinstance(d, Definition):
                        continue
                    for name in self.closured.get(d.fullns, []):
                        return_ns = utils.join_ns(name, utils.constants.RETURN_NAME)

                        if self.closured.get(return_ns, None) == None:
                            continue

                        new_previous_names.update(self.closured.get(return_ns))

                        for prev_name in previous_names:
                            pos_arg_names = d.name_pointer.get_pos_arg(0)
                            if not pos_arg_names:
                                continue
                            for name in pos_arg_names:
                                arg_def = self.def_manager.get(name)
                                if arg_def is not None:
                                    arg_def.name_pointer.add(prev_name)
                previous_names = new_previous_names

        super().visit_FunctionDef(node)
        logger.debug("Exit PreProcessor.visit_FunctionDef")

    def visit_ClassDef(self, node):
        logger.debug("In PreProcessor.visit_ClassDef")
        logger.debug("CC-1")
        # create a definition for the class (node.name)
        cls_def = self.def_manager.handle_class_def(self.current_ns, node.name)
        logger.debug("CC-2")

        # iterate bases to compute MRO for the class
        cls = self.class_manager.get(cls_def.fullns)
        if not cls:
            #logger.debug("CC-3")
            cls = self.class_manager.create(cls_def.fullns, self.modname)
        #logger.debug("CC-4")

        cls.clear_mro()
        #logger.debug("CC-5")
        for base in node.bases:
            #logger.debug("CC-6")
            # all bases are of the type ast.Name
            self.visit(base)

            bases = self.decode_node(base)
            #logger.debug("CC-7")
            for base_def in bases:
                #logger.debug("CC-8")
                if not isinstance(base_def, Definition):
                    continue
                #logger.debug("CC-9")
                names = set()
                if base_def.name_pointer.values:
                    #logger.debug("CC-10")
                    names = base_def.name_pointer.values
                    #logger.debug("CC-11")
                else:
                    #logger.debug("CC-12")
                    names.add(base_def.fullns)
                    #logger.debug("CC-13")
                logger.debug("CC-14")
                for name in names:
                    # add the base as a parent
                    #logger.debug("CC-15")
                    cls.add_parent(name)
                    #logger.debug("CC-16")

                    # add the base's parents
                    parent_cls = self.class_manager.get(name)
                    #logger.debug("CC-17")
                    if parent_cls:
                        #logger.debug("CC-18")
                        parent_cls_mro = parent_cls.get_mro()
                        #logger.debug("CC-18.1")
                        if parent_cls_mro == cls.mro:
                            continue
                        cls.add_parent(parent_cls_mro)
                        #logger.debug("CC-19")

        #logger.debug("CC-20")
        cls.compute_mro()
        #logger.debug("CC-21")

        super().visit_ClassDef(node)
        #logger.debug("CC-22")
        logger.debug("Exit PreProcessor.visit_ClassDef")

    def visit_List(self, node):
        logger.debug("In PreProcessor.visit_List")
        # Works similarly with dicts
        current_scope = self.scope_manager.get_scope(self.current_ns)
        list_counter = current_scope.inc_list_counter()
        list_name = utils.get_list_name(list_counter)
        list_full_ns = utils.join_ns(self.current_ns, list_name)

        # create a scope for the list
        list_scope = self.scope_manager.create_scope(list_full_ns, current_scope)

        # create a list definition
        list_def = self.def_manager.get(list_full_ns)
        if not list_def:
            list_def = self.def_manager.create(list_full_ns, utils.constants.NAME_DEF)
        current_scope.add_def(list_name, list_def)

        self.name_stack.append(list_name)
        for idx, elt in enumerate(node.elts):
            self.visit(elt)
            key_full_ns = utils.join_ns(list_def.fullns, utils.get_int_name(idx))
            key_def = self.def_manager.get(key_full_ns)
            if not key_def:
                key_def = self.def_manager.create(key_full_ns, utils.constants.NAME_DEF)

            decoded_elt = self.decode_node(elt)
            for v in decoded_elt:
                if isinstance(v, Definition):
                    key_def.name_pointer.add(v.fullns)
                else:
                    key_def.literal_pointer.add(v)

        self.name_stack.pop()
        logger.debug("Exit PreProcessor.visit_List")

    def visit_Dict(self, node: ast.Dict):
        logger.debug("In PreProcessor.visit_Dict")
        # 1. create a scope using a counter
        # 2. Iterate keys and add them as children of the scope
        # 3. Iterate values and makes a points to connection with the keys
        current_scope = self.scope_manager.get_scope(self.current_ns)
        dict_counter = current_scope.inc_dict_counter()
        dict_name = utils.get_dict_name(dict_counter)
        dict_full_ns = utils.join_ns(self.current_ns, dict_name)

        # create a scope for the dict
        dict_scope = self.scope_manager.create_scope(dict_full_ns, current_scope)

        # Create a dict definition
        dict_def = self.def_manager.get(dict_full_ns)
        if not dict_def:
            dict_def = self.def_manager.create(dict_full_ns, utils.constants.NAME_DEF)
        # add it to the current scope
        current_scope.add_def(dict_name, dict_def)

        self.name_stack.append(dict_name)
        for key, value in zip(node.keys, node.values):
            if key:
                self.visit(key)
            if value:
                self.visit(value)
            decoded_key = self.decode_node(key)
            decoded_value = self.decode_node(value)

            # iterate decoded keys and values
            # to do the assignment operation
            for k in decoded_key:
                if isinstance(k, Definition):
                    # get literal pointer
                    names = k.literal_pointer.values
                else:
                    
                    if isinstance(k, list):
                        continue
                    names = set()
                    names.add(k)
                for name in names:
                    # create a definition for the key
                    if isinstance(name, int):
                        name = utils.get_int_name(name)
                    key_full_ns = utils.join_ns(dict_def.fullns, str(name))
                    key_def = self.def_manager.get(key_full_ns)
                    if not key_def:
                        key_def = self.def_manager.create(key_full_ns, utils.constants.NAME_DEF)
                    dict_scope.add_def(str(name), key_def)
                    for v in decoded_value:
                        if isinstance(v, Definition):
                            key_def.name_pointer.add(v.fullns)
                        else:
                            key_def.get_lit_pointer().add(v)
        self.name_stack.pop()
        logger.debug("Exit PreProcessor.visit_Dict")

    def update_parent_classes(self, defi):
        logger.debug("In PreProcessor.update_parent_classes")
        cls = self.class_manager.get(defi.fullns)
        if not cls:
            return
        current_scope = self.scope_manager.get_scope(defi.fullns)
        for parent in cls.get_mro():
            parent_def = self.def_manager.get(parent)
            if not parent_def:
                continue
            parent_scope = self.scope_manager.get_scope(parent)
            if not parent_scope:
                continue
            parent_items = list(parent_scope.get_defs().keys())
            for key, child_def in current_scope.get_defs().items():
                if key == "__init__":
                    continue
                # resolve name from the parent_def
                names = self.find_cls_fun_ns(parent_def.fullns, key)

                new_ns = utils.join_ns(parent_def.fullns, key)
                new_def = self.def_manager.get(new_ns)
                if not new_def:
                    new_def = self.def_manager.create(new_ns, utils.constants.NAME_DEF)

                new_def.name_pointer.add_set(names)
                new_def.name_pointer.add(child_def.fullns)

        logger.debug("Exit PreProcessor.update_parent_classes")

    def analyze_submodules(self) -> None:
        logger.debug("In PreProcessor.analyze_submodules")
        super().analyze_submodules(PostProcessor, self.import_manager,
                self.scope_manager, self.def_manager, self.class_manager,
                self.module_manager, modules_analyzed=self.get_modules_analyzed())
        logger.debug("Exit PreProcessor.analyze_submodules")

    def analyze(self) -> None:
        logger.debug("In PreProcessor.analyze")
        try:
            self.visit(ast.parse(self.contents, self.filename))
        except SyntaxError:
            # Handle potential syntax errors in the module. Do not
            # crash in the event a SyntaxError exists in the loaded module.
            pass
        self.analyze_submodules()
        logger.debug("Exit PreProcessor.analyze")
