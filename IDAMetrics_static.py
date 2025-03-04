"""
IDAMetrics_static IDA plugin ver. 0.7

Copyright (c) 2015, Maksim Shudrak (mxmssh@gmail.com)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies,
either expressed or implied, of the FreeBSD Project.
"""
"""
This IDA script collects static software complexity metrics for binary executable.

Supported the following metrics:
    1. Lines of code (function/module)
    2. Average lines of code per basic block (module)
    3. Basic blocks count (function/module)
    4. Functions count (module)
    5. Conditions count (function/module)
    6. Assignments count (function/module)
    7. Cyclomatic complexity metric (function/module)
    8. Cyclomatic complexity modified metric (function/module)
    9. Jilb's metric (function/module)
    10. ABC metric (function/module)
    11. Pivovarsky metric (function/module)
    12. Halstead metric (function/module)
    13. Harrison metric (function/module)
    14. Boundary value metric (function/module)
    15. Span metric (function/module)
    16. Global variables access count (function/module)
    17. Oviedo metric (function/module)
    18. Chepin metric (function/module)
    19. Card & Glass metric (function/module)
    20. Henry & Cafura metric (function/module)
    21. Cocol metric (function/module)
Additional functionality:
     - node graph generation (function)
     - basic block boundaries generation (function)
"""

import sys
import idc
import idaapi
import idautils
import ida_idp
import math
import gc
from time import strftime
from collections import defaultdict
from idaapi import *
from enum import Enum



class inType(Enum):
    OTHERS = 0
    CALL = 1
    CONDITIONAL_BRANCH = 2
    UNCONDITIONAL_BRACH = 3
    ASSIGNMENT = 4
    COMPARE = 5



__EA64__ = idaapi.BADADDR == 0xFFFFFFFFFFFFFFFF

CF_CHG = ida_idp.CF_CHG1 | ida_idp.CF_CHG2 | ida_idp.CF_CHG3 | ida_idp.CF_CHG4 | ida_idp.CF_CHG5 | ida_idp.CF_CHG6  # | ida_idp.CF_CHG7 | ida_idp.CF_CHG8
CF_USE = ida_idp.CF_USE1 | ida_idp.CF_USE2 | ida_idp.CF_USE3 | ida_idp.CF_USE4 | ida_idp.CF_USE5 | ida_idp.CF_USE6  # | ida_idp.CF_USE7 | ida_idp.CF_USE8

FUNCATTR_END = 4  # function end address
ARGUMENT_SIZE = 4
CSV = True

if __EA64__:
    FUNCATTR_END = 8
    ARGUMENT_SIZE = 8

metrics_list = [
    "loc", "bbls", "calls", "condit", "assign", "cc", "cc_mod", "jilb", "abc",
    "pi", "h", "harr", "bound", "span", "global", "oviedo", "chepin", "c&s",
    "h&c", "cocol"
]
metrics_names = ["Lines of code", "Basic blocks count", "Routines calls count", "Conditions count",\
                 "Assignments count", "Cycl. complexity", "Cycl. complexity mod.", "Jilb", "ABC", \
                 "Pivovarsky", "Halstead", "Harrison", "Boundary values", "span metric", \
                 "Global vars access count", "Oviedo", "Chepin", "Card & Glass", "Henry & Cafura",\
                 "Cocol"]


class Halstead_metric:
    def __init__(self):
        self.n1 = 0
        self.n2 = 0
        self.N1 = 0
        self.N2 = 0
        self.V = 0
        self.Ni = 0
        self.D = 0
        self.E = 0
        self.B = 0

    def calculate(self):
        n = self.n1 + self.n2
        N = self.N1 + self.N2
        try:
            self.Ni = self.n1 * math.log(self.n1, 2) + self.n2 * math.log(
                self.n2, 2)
        except:
            print(
                "WARNING: Ni value for Halstead metric is too large to calculate"
            )
        self.V = N * math.log(n, 2)
        if self.n2 != 0:
            self.D = (self.n1 / 2) * (self.N2 / self.n2)
        else:
            print(
                "WARNING: n2 value for Halstead metric is 0. Skip evaluation for this routine"
            )
        self.E = self.D * self.V
        self.B = (self.E**(2.0 / 3.0)) / 3000


global_vars_dict = {}


class Metrics_function:
    def __init__(self, function_ea, metrics_mask):
        self.function_name = idc.get_func_name(function_ea)
        self.function_ea = function_ea
        self.function_start = function_ea
        self.function_end = idc.find_func_end(self.function_ea)
        self.metrics_mask = metrics_mask
        self.loc_count = 0
        self.bbl_count = 0
        self.condition_count = 0
        self.calls_count = 0
        self.R = 0.0
        self.CC = 0
        self.CL = 0
        self.assign_count = 0
        self.ABC = 0
        self.CC_modified = 0
        self.Pivovarsky = 0
        self.Halstead_basic = Halstead_metric()
        self.Harrison = 0
        self.boundary_values = 0.0
        self.span_metric = 0
        self.vars_local = dict()
        self.vars_args = dict()
        self.Oviedo = 0
        self.Chepin = 0
        self.global_vars_access = 0
        self.global_vars_used = dict()
        self.global_vars_metric = 0.0
        self.bbls_boundaries = dict()
        self.CardnGlass = 0
        self.fan_in_i = 0
        self.fan_in_s = 0
        self.fan_out_i = 0
        self.calls_dict = dict()
        self.fan_out_s = 0
        self.HenrynCafura = 0
        self.Cocol = 0

    def start_analysis(self):
        """
        The function calculates all supported metrics.
        @function_ea - function address
        @return - function metrics structure
        """
        function_ea = self.function_ea
        f_start = function_ea
        f_end = idc.find_func_end(function_ea)

        edges = set()
        boundaries = set((f_start, ))
        mnemonics = dict()
        operands = dict()
        switchea = set()
        node_graph = None
        cases_in_switches = 0

        chunks = self.enumerate_function_chunks()
        # For each defined chunk in the function.
        for chunk in chunks:
            for head in idautils.Heads(*chunk):
                # If the element is an instruction
                if head == idaapi.BADADDR:
                    # the idautils.Heads is a generator, have to check during iterating
                    raise Exception("Invalid head for parsing")
                if is_code(ida_bytes.get_full_flags(head)):
                    self.loc_count += 1
                    # Get the references made from the current instruction
                    # and keep only the ones local to the function.
                    refs = idautils.CodeRefsFrom(head, 0)
                    refs_filtered = set()
                    for ref in refs:
                        if ref == idaapi.BADADDR:
                            print("Invalid reference for head", head)
                            raise Exception("Invalid reference for head")
                        for chunk_filter in chunks:
                            if ref >= chunk_filter[0] and ref < chunk_filter[1]:
                                refs_filtered.add(ref)
                                break
                    refs = refs_filtered
                    # Get instruction type and increase metrics
                    instruction_type = self.GetInstructionType(head)
                    if instruction_type == inType.CONDITIONAL_BRANCH:
                        self.condition_count += 1
                    elif instruction_type == inType.CALL:
                        self.calls_count += 1
                        # set dict of function calls
                        opnd_type = idc.get_operand_type(head, 0)
                        opnd = get_operand_value(head, 0)
                        if opnd_type == idc.o_reg:
                            key = f"reg_{opnd}"
                        elif opnd_type == idc.o_phrase:
                            key = f"phrase_{opnd}"
                        elif opnd_type == idc.o_displ:
                            key = f"displ_{opnd}"
                        elif opnd_type in [idc.o_mem, idc.o_imm, idc.o_far, idc.o_near]:
                            key = f"mem_{opnd}"
                        else:
                            print("Impossible@", head)
                            raise Exception("Cthulhu has awakened")
                        self.calls_dict[key] = self.calls_dict.get(key, 0) + 1
                    elif instruction_type == inType.ASSIGNMENT:
                        self.assign_count += 1
                    # Get the mnemonic and increment the mnemonic count
                    mnem = idc.print_insn_mnem(head)
                    mnemonics[mnem] = mnemonics.get(mnem, 0) + 1
                    # switch case count
                    switch_info = ida_nalt.get_switch_info(head)
                    if switch_info is not None and switch_info.startea not in switchea:
                        switchea.add(switch_info.startea)
                        cases_in_switches += switch_info.ncases
                    if instruction_type != inType.CONDITIONAL_BRANCH and instruction_type != inType.CALL:
                        ops = self.get_instr_operands(head)
                        for idx, (op, op_type) in enumerate(ops):
                            operands[op] = operands.get(op, 0) + 1
                            if op_type == idc.o_mem:
                                # TODO: refactor this
                                if self.is_var_global(
                                        idc.get_operand_value(head, idx),
                                        head) and "__" not in op:
                                    global_vars_dict[op] = operands.get(op,
                                                                        0) + 1
                                    self.global_vars_used.setdefault(
                                        op, []).append(hex(head))
                                    self.global_vars_access += 1
                                elif "__" not in op:
                                    # static variable
                                    name = op
                                    self.vars_local.setdefault(name,
                                                               []).append(
                                                                   hex(head))
                            elif op_type == idc.o_phrase or op_type == idc.o_displ:
                                name = self.get_local_var_name(op, head)
                                if name:
                                    self.vars_local.setdefault(name,
                                                               []).append(
                                                                   hex(head))

                    if refs:
                        # If the flow continues also to the next (address-wise)
                        # instruction, we add a reference to it.
                        # For instance, a conditional jump will not branch
                        # if the condition is not met, so we save that
                        # reference as well.
                        next_head = idc.next_head(head, chunk[1])
                        # if next_head == idaapi.BADADDR:
                            # print("Invalid next head after ", head)
                            # raise Exception("Invalid next head")
                        if is_flow(ida_bytes.get_full_flags(next_head)):
                            refs.add(next_head)

                        # Update the boundaries found so far.
                        boundaries.update(refs)
                        # For each of the references found, and edge is
                        # created.
                        for r in refs:
                            # If the flow could also come from the address
                            # previous to the destination of the branching
                            # an edge is created.
                            if is_flow(ida_bytes.get_full_flags(r)):
                                prev_head = idc.prev_head(r, chunk[0])
                                if prev_head == idaapi.BADADDR:
                                    edges.add((hex(head), hex(r)))
                                    #raise Exception("invalid reference to previous instruction for", hex(r))
                                else:
                                    edges.add((hex(prev_head), hex(r)))
                            edges.add((hex(head), hex(r)))
        # i#7: New algorithm of edges and boundaries constructing is required..
        # Now boundaries and edges are making by using internal IDA functionality
        # but it doesn't work for functions which have jumps beyond function boundaries
        # (or jumps to "red" areas of code). Now we're generating warning in such
        # situations but we need to manually parse all instructions.
        bbls = self.get_bbls(chunks, boundaries, edges)
        # save bbls boundaries in dict
        for bbl in bbls:
            self.bbls_boundaries[bbl[0]] = [x for x in bbl]
        #Cyclomatic complexity CC = E - V + 2
        if self.metrics_mask["cc"] == 1 or self.metrics_mask["cocol"] == 1:
            self.CC = len(edges) - len(boundaries) + 2

        # R measure
        self.R = len(edges) / len(boundaries)
        #Basic blocks count
        self.bbl_count = len(boundaries)
        #Jilb's metric: cl = CL/n
        if self.metrics_mask["jilb"] == 1:
            if (self.loc_count == 0):
                self.CL = 0
            else:
                self.CL = (float(self.condition_count) + \
                                   self.calls_count)/self.loc_count
        # ABC metric: ABC = sqrt(A*A + B*B + C*C)
        if self.metrics_mask["abc"] == 1:
            self.ABC = pow(self.assign_count, 2) +\
                                   pow(self.condition_count, 2) +\
                                   pow(self.calls_count, 2)
            self.ABC = math.sqrt(self.ABC)
        # Create node graph
        if self.metrics_mask["harr"] == 1 or self.metrics_mask[
                "bound"] == 1 or self.metrics_mask["pi"] == 1:
            node_graph = self.make_graph(edges, bbls, boundaries)

        #Harrison metric: f = sum(ci) i: 0...n
        if self.metrics_mask["harr"] == 1:
            self.Harrison = self.get_harrison_metric(node_graph, bbls)

        #boundary values metric: Sa = sum(nodes_complexity)
        if self.metrics_mask["bound"] == 1:
            self.boundary_values = self.get_boundary_value_metric(node_graph)

        #CC_modified assumes switch (without default) as 1 edge and 1 node
        if self.metrics_mask["cc_mod"] == 1:
            if cases_in_switches:
                self.CC_modified = (len(edges) -
                                    ((cases_in_switches - 1) * 2)) - (
                                        len(boundaries) -
                                        (cases_in_switches - 1)) + 2
            else:
                self.CC_modified = self.CC
        #Pivovarsky metric: N(G) = CC_modified + sum(pi) i: 0...n
        if self.metrics_mask["pi"] == 1:
            self.Pivovarsky = self.CC_modified + self.get_boundary_value_metric(
                node_graph, True)

        #Halstead metric. see http://en.wikipedia.org/wiki/Halstead_complexity_measures
        if self.metrics_mask["h"] == 1 or self.metrics_mask["cocol"] == 1:
            self.Halstead_basic.N1 = self.loc_count
            self.Halstead_basic.n1 = len(mnemonics)
            self.Halstead_basic.n2 = len(operands)
            if len(operands) != 0:
                self.Halstead_basic.N2 = sum(v for v in operands.values())
                self.Halstead_basic.calculate()

        # Span metric
        if self.metrics_mask["span"] == 1:
            self.span_metric = self.get_span_metric(self.bbls_boundaries)

        # Oviedo metric C = aCF + bsum(DFi)
        if self.metrics_mask["oviedo"] == 1:
            self.Oviedo = len(edges) + self.get_oviedo_df(self.vars_local)

        # Chepin metric Q= P+2M+3C
        if self.metrics_mask["chepin"] == 1:
            self.Chepin = self.get_chepin(self.vars_local, function_ea)

        # Henry and Cafura metric
        if self.metrics_mask["h&c"] == 1 or self.metrics_mask["c&s"] == 1:
            self.HenrynCafura = self.get_henryncafura_metric(function_ea)

        # Card and Glass metric C = S + D
        if self.metrics_mask["c&s"] == 1:
            self.CardnGlass = pow((self.fan_out_i + self.fan_out_s), 2) +\
                                  (len(self.vars_args))/(self.fan_out_i + self.fan_out_s + 1)
        #free memory
        if node_graph:
            node_graph.clear()
        self.vars_local.clear()
        self.vars_args.clear()
        self.global_vars_used.clear()
        self.calls_dict.clear()
        mnemonics.clear()
        operands.clear()
        edges.clear()
        boundaries.clear()
        gc.collect()

    def enumerate_function_chunks(self):
        """
        The function gets a list of chunks for the function.
        @f_start - first address of the function
        @return - list of chunks
        """
        # Enumerate all chunks in the function
        chunks = list()
        next_chunk = idc.first_func_chunk(self.function_ea)
        while next_chunk != idaapi.BADADDR:
            chunks.append(
                (next_chunk, idc.get_fchunk_attr(next_chunk,
                                                 idc.FUNCATTR_END)))
            next_chunk = idc.next_func_chunk(self.function_ea, next_chunk)
        return chunks

    def get_chepin(self, local_vars, function_ea):
        '''
        The function calculates Chepin metric
        @local_vars - a dictionary of local variables
        @function_ea - function entry address
        @function_metrics - function metrics structure
        @return - Chepin value
        '''
        chepin = 0
        p = 0
        m = 0
        c = 0
        tmp_dict = dict()
        var_args_tmp = dict()
        (p,
         var_args_tmp) = self.get_function_args_count(function_ea, local_vars)
        for local_var in local_vars:
            usage_list = local_vars.get(local_var, None)
            if usage_list == None:
                print("WARNING: empty usage list for ", local_var)
                continue
            for instr_addr in usage_list:
                instr_mnem = idc.print_insn_mnem(int(instr_addr, 16))
                if instr_mnem.startswith('cmp') or instr_mnem.startswith(
                        'test'):
                    tmp_dict.setdefault(local_var, []).append(instr_addr)

        for var_arg in var_args_tmp:
            if var_arg in local_vars:
                del local_vars[var_arg]
        for cmp_var in tmp_dict:
            if cmp_var in local_vars:
                del local_vars[cmp_var]

        c = len(tmp_dict)
        m = len(local_vars)
        chepin = p + 2 * m + 3 * c
        return chepin

    def get_henryncafura_metric(self, function_ea):
        '''
        The function performs evaluation of Henry&Cafura metric
        @function_ea - function entry address
        @function_metrics - function_metrics structure
        @return - Henry&Cafura metric
        '''
        self.fan_out_s = len(self.calls_dict)
        refs_to = idautils.CodeRefsTo(function_ea, 0)
        self.fan_in_s = sum(1 for y in refs_to)

        (count, self.vars_args) = self.get_function_args_count(
            function_ea, self.vars_local)

        # check input args
        (read, write) = self.get_unique_vars_read_write_count(self.vars_args)
        self.fan_in_i += read
        self.fan_out_i += write
        # check global variables list
        (read,
         write) = self.get_unique_vars_read_write_count(self.global_vars_used)
        self.fan_in_i += read
        self.fan_out_i += write

        fan_in = self.fan_in_s + self.fan_in_i
        fan_out = self.fan_out_s + self.fan_out_i
        return self.CC + pow((fan_in + fan_out), 2)

    def get_bbl_head(self, head):
        """
        The function returns address of the head instruction
        for the basic block.
        @head - address of arbitrary instruction in the basic block.
        @return - head address of the basic block.
        """

        while True:
            prev_head = idc.prev_head(head, 0)
            if not is_flow(ida_bytes.get_full_flags(prev_head)):
                break
            head = prev_head
            if prev_head >= SegEnd(head):
                raise Exception("Can't identify bbl head")

        if prev_head == idaapi.BADADDR:
            return head
        else:
            return prev_head

    def get_subgraph_nodes_count(self, node, node_graph, nodes_passed):
        """
        The function calculates total count of nodes in the subgraph for
        selected node.
        @node - first node to get subgraph
        @node_graph - node graph dictionary (result of make_graph function)
        @nodes_passed - list of passed nodes
        @return - total count of nodes in the subgraph
        """
        nodes_count = 0
        if node in nodes_passed:
            #already passed
            return 1
        else:
            nodes_passed.append(node)
        child_nodes = node_graph.get(node, None)
        if child_nodes != None:
            for child_node in child_nodes:
                if child_node in nodes_passed:
                    continue
                nodes_count += self.get_subgraph_nodes_count(
                    child_node, node_graph, nodes_passed)
                nodes_count += 1
        return nodes_count

    def get_boundary_value_metric(self, node_graph, pivovarsky=False):
        """
        Function returns absolute boundary value metric or Pi value for
        Pivovarsky metric.
        @node_graph - node graph dictionary (result of make_graph function)
        @pivovarsky - if true function calculates Pivovarsky Pi operand
        @return - boundary value or Pi value
        """
        boundary_value = 0
        for node in node_graph:
            childs = node_graph.get(node, None)
            if childs == None:
                continue
            out_edges_count = len(childs)
            if pivovarsky:
                if out_edges_count == 2:
                    boundary_value += self.get_subgraph_nodes_count(
                        node, node_graph, list())
            else:
                if out_edges_count >= 2:
                    boundary_value += self.get_subgraph_nodes_count(
                        node, node_graph, list())
                else:
                    boundary_value += 1
        if not pivovarsky:
            boundary_value -= 1  #exclude terminal node for boundary value metric
        return boundary_value

    def get_node_complexity(self, node, node_graph, bbls_dict, nodes_passed):
        """
        This function is very similar with get_subgraph_nodes_count but it uses
        to calculate Harrison metric.
        @node - node address to get node complexity
        @node_graph - node graph dictionary (result of make_graph function)
        @bbls_dict - basic block boundaries dictionary
        @nodes_passed - list of passed nodes_count
        @return - node complexity by using loc measure and list of passed nodes
        """
        loc_measure = 0
        # i#3: add more initial complexity metrics e.g. Halstead
        if node in nodes_passed:
            #already passed
            return 0, nodes_passed
        else:
            nodes_passed.append(node)
        child_nodes = node_graph.get(node, None)
        if child_nodes != None:
            for child_node in child_nodes:
                if child_node in nodes_passed:
                    continue
                bbls_node = bbls_dict.get(child_node, None)
                if bbls_node == None:
                    print("WARNING: couldn't find bbl for child node: ",
                          child_node)
                    loc_measure += 0
                else:
                    loc_measure += len(bbls_node)
                    loc_measure += self.get_node_complexity(
                        child_node, node_graph, bbls_dict, nodes_passed)
        return loc_measure

    def get_harrison_metric(self, node_graph, bbls):
        """
        The function calculates Harrison metric.
        @node_graph - node graph dictionary (result of make_graph function)
        @bbls - bbls set
        @return - Harrison metric
        """
        bbls_dict = dict()
        loc_measure = 0
        for bbl in bbls:
            bbls_dict[bbl[0]] = [x for x in bbl]
        for node in node_graph:
            childs = node_graph.get(node, None)
            if childs == None or len(childs) != 2:
                loc_measure_node = bbls_dict.get(node, None)
                if loc_measure_node != None:
                    loc_measure += len(loc_measure_node)
                else:
                    print("WARNING: couldn't find bbl for node: ", node)
            else:
                loc_measure += self.get_node_complexity(
                    node, node_graph, bbls_dict, list())
                bbls_predicate_node = bbls_dict.get(node, None)
                if bbls_predicate_node == None:
                    print("WARNING: couldn't find bbl for predicate node: ",
                          node)
                else:
                    loc_measure += len(bbls_predicate_node)
        return loc_measure

    # i#4 Support graphs with several terminal nodes
    # i#5 Ignore nodes without incoming edges
    def make_graph(self, edges, bbls, boundaries):
        """
        The function makes nodes graph by using edges,
        bbls and boundaries sets.
        @edges - set of edges
        @bbls - set of bbls
        @boundaries - set of boundaries
        @return node graph
        """
        node_graph = dict()
        edges_dict = dict()
        bbls_dict = dict()

        # i#6 This function needs re-factoring. Now it has ugly
        # additional functionality to make the graph correct for
        # functions with chunks and to add terminal nodes. (xref i#7)

        for edge_from, edge_to in edges:
            if edge_from == hex(idaapi.BADADDR):
                raise Exception("Invalid edge reference", edge_from)
            edges_dict.setdefault(edge_from, []).append(edge_to)
        for bbl in bbls:
            bbls_dict[bbl[len(bbl) - 1]] = [x for x in bbl]
        boundaries_list = [hex(x) for x in boundaries]

        for edge_from in edges_dict:
            node_edges_to = edges_dict[edge_from]
            if node_edges_to == None:
                raise Exception("Error when creating node graph")
            # check for additional chunks (xref i#6)
            if edge_from not in boundaries_list:
                bbl_edge_from = bbls_dict.get(edge_from, None)
                if bbl_edge_from == None:
                    print("WARNING: Can't find bbl for ", edge_from)
                else:
                    node_graph[bbl_edge_from[0]] = node_edges_to
            else:
                node_graph[edge_from] = node_edges_to

        if len(node_graph) == 0 and len(edges_dict) == 0 and len(
                boundaries_list) == 1:
            node_graph[boundaries_list[
                0]] = None  #it means that graph has only single root node
        elif len(node_graph) == 0 and len(edges_dict) != 0:
            raise Exception("Error when creating node graph")
        #add terminal nodes (xref i#6)
        for bbl in bbls:
            check_bbl = node_graph.get(bbl[0], None)
            if check_bbl == None:
                node_graph[bbl[0]] = None
        return node_graph

    def get_bbls(self, chunks, boundaries, edges):
        """
        Set bbls using edges and boundaries
        @chunks - a list of function chunks
        @boundaries - a list of function boundaries (see get_static_metrics)
        @edges - a list of function edges (see get_static_metrics)
        @return - a set of bbls boundaries
        """
        bbls = []
        bbl = []
        # NOTE: We can handle if jump xrefs to chunk address space.
        for chunk in chunks:
            for head in idautils.Heads(*chunk):
                if head in boundaries or head in edges:
                    if len(bbl) > 0:
                        bbls.append(bbl)
                        bbl = []
                    bbl.append(hex(head))
                elif self.GetInstructionType(
                        head) == inType.CONDITIONAL_BRANCH:
                    bbl.append(hex(head))
                    bbls.append(bbl)
                    bbl = []
                else:
                    bbl.append(hex(head))
        # add last basic block
        if len(bbl) > 0:
            bbls.append(bbl)
        return bbls

    def get_instr_operands(self, head):
        """
        @head - instruction address
        @return - the function returns list of variables which is
        used in the instruction
        """
        instr_op = list()
        for i in range(6):
            op = idc.print_operand(head, i)
            if op != "":
                instr_op.append((op, idc.get_operand_type(head, i)))
        return instr_op

    def is_operand_called(self, op, bbl):
        '''
        The function checks whether operand used for call instruction in the
        following instructions or not.
        @op - operand
        @bbl - list of instructions in bbl
        @return - True if used
        '''
        for instr in bbl:
            instr_type = self.GetInstructionType(int(instr, 16))
            if instr_type == inType.CALL or instr_type == inType.CONDITIONAL_BRANCH:
                instr_ops = self.get_instr_operands(int(instr, 16))
                if op in instr_ops:
                    return True
                #trying to replace ds: and check it again
                op = op.replace("ds:", "")
                comment = idc.GetDisasm(int(instr, 16))
                if comment != None and op in comment:
                    return True
        return False

    def get_function_args_count(self, function_ea, local_vars):
        """
        The function returns count of function arguments
        @function_ea - function entry point
        @local_vars - local variables dictionary
        @return - function arguments count
        """
        # i#9 Now, we can't identify fastcall functions.

        function_args_count = 0
        args_dict = dict()
        for local_var in local_vars:
            usage_list = local_vars.get(local_var, None)
            if usage_list == None:
                print("WARNING: empty usage list for ", local_var)
                continue
            for head in usage_list:
                ops = self.get_instr_operands(int(head, 16))
                for idx, (op, type) in enumerate(ops):
                    if op.count("+") == 1:
                        value = idc.get_operand_value(int(head, 16), idx)
                        if value < (15 * ARGUMENT_SIZE) and "ebp" in op:
                            args_dict.setdefault(local_var, []).append(head)
                    elif op.count("+") == 2:
                        if "arg" in local_var:
                            args_dict.setdefault(local_var, []).append(head)
                    else:
                        continue

        function_args_count = len(args_dict)
        if function_args_count:
            return function_args_count, args_dict

        #TODO Check previous algorithm here
        f_end = idc.find_func_end(function_ea)
        f_end = idc.prev_head(f_end, 0)
        instr_mnem = idc.print_insn_mnem(f_end)
        #stdcall ?
        if "ret" in instr_mnem:
            ops = self.get_instr_operands(f_end)
            if len(ops) == 1:
                for op, type in ops:
                    op = op.replace("h", "")
                    function_args_count = int(op, 16) / ARGUMENT_SIZE
                    return function_args_count, args_dict
        #cdecl ?
        refs = idautils.CodeRefsTo(function_ea, 0)
        for ref in refs:
            #trying to find add esp,x signature after call
            head = idc.next_head(ref, idaapi.BADADDR)
            if head:
                disasm = idc.GetDisasm(head)
                if "add" in disasm and "esp," in disasm:
                    ops = self.get_instr_operands(head)
                    op, type = ops[1]
                    if op:
                        op = op.replace("h", "")
                        function_args_count = int(op, 16) / ARGUMENT_SIZE
                        return function_args_count, args_dict
        return function_args_count, args_dict

    def get_span_metric(self, bbls_dict):
        """
        The function calculates span metric.
        @bbls_dict - basic blocks dictionary
        @return - span metric
        """
        span_metric = 0
        for bbl_key, bbl in bbls_dict.items():
            for head in bbl:
                instr_op = self.get_instr_operands(int(head, 16))
                instr_type = self.GetInstructionType(int(head, 16))
                if instr_type == inType.CALL or instr_type == inType.CONDITIONAL_BRANCH:
                    continue
                for op, type in instr_op:
                    if self.is_operand_called(op, bbl):
                        continue
                    if type >= idc.o_mem and type <= idc.o_displ:
                        span_metric += 1
        return span_metric

    def is_var_global(self, operand, head):
        '''
        The function checks whether operand global or not.
        @return - True if global
        '''
        if operand == -1:
            return False
        refs = idautils.DataRefsTo(operand)
        if len(list(refs)) > 1:
            return True
        return False

    def get_local_var_name(self, operand, head):
        '''
        The function returns variable name which is used in operand
        @operand - operand string representation
        @head - instruction head for debugging
        @return - variable name
        '''
        # i#8 Now we can't identify variables which is handled by registers.
        # We can only identify stack local variables.
        operand = operand.replace(" ", "")
        name = ""

        if operand.count("+") == 1:
            # [base reg+name]
            name = operand[operand.find("+") + 1:operand.find("]")]
        elif operand.count("+") == 2:
            # [base reg + reg + name]
            name = operand[operand.rfind("+") + 1:operand.find("]")]
        elif operand.count("+") > 2:
            #try to find var_XX mask
            if "var_" in operand:
                # [reg1+x*reg2+arg_XX+value] or [reg1+x*reg2+value+arg_XX]
                if operand.find("var_") > operand.rfind("+"):
                    operand = operand[operand.find("var_"):operand.find("]")]
                else:
                    operand = operand[operand.find("var_"):operand.rfind("+")]
            #try to find arg_XX mask
            elif "arg_" in operand:
                # [reg1+x*reg2+arg_XX+value] or [reg1+x*reg2+value+arg_XX]
                if operand.find("var_") > operand.rfind("+"):
                    operand = operand[operand.find("arg_"):operand.find("]")]
                else:
                    operand = operand[operand.find("arg_"):operand.rfind("+")]
            else:
                print("WARNING: unknown operand mask ", operand, hex(head))
                name = None
        else:
            name = None
        return name

    def get_oviedo_df(self, local_vars):
        '''
        The function calculates Oviedo's DF value
        @local_vars - a dictionary of local variables for function
        @return - Oviedo's DF value
        '''
        oviedo_df = 0
        # get local variables usage count, except initialization, such as:
        # mov [ebp+var_0], some_value
        for local_var in local_vars:
            usage_list = local_vars.get(local_var, None)
            if usage_list == None:
                print("WARNING: empty usage list for ", local_var)
                continue
            for instr_addr in usage_list:
                instr_mnem = idc.print_insn_mnem(int(instr_addr, 16))
                if instr_mnem.startswith('mov'):
                    # get local var position
                    operands = self.get_instr_operands(int(instr_addr, 16))
                    for idx, (operand, type) in enumerate(operands):
                        if local_var in operand and idx == 0:
                            oviedo_df -= 1
                            break
            oviedo_df += len(usage_list)
        return oviedo_df

    def get_unique_vars_read_write_count(self, vars_dict):
        '''
        The function performs evaluation of read/write count for each
        variable in dictionary.
        @vars_dict - a dictionary of variable to get count
        @return - two dictionaries of read and write for each variable
        '''
        tmp_dict_read = dict()
        tmp_dict_write = dict()
        for arg_var in vars_dict:
            usage_list = vars_dict.get(arg_var, None)
            if usage_list == None:
                print("WARNING: empty usage list for ", arg_var)
                continue
            for instr_addr in usage_list:
                instr_type = self.GetInstructionType(int(instr_addr, 16))
                if instr_type == inType.ASSIGNMENT:
                    #detect operand position
                    ops = self.get_instr_operands(int(instr_addr, 16))
                    for idx, (op, type) in enumerate(ops):
                        if arg_var in op and idx == 0:
                            tmp_dict_write[arg_var] = tmp_dict_write.get(
                                arg_var, 0) + 1
                            break
                        else:
                            tmp_dict_read[arg_var] = tmp_dict_read.get(
                                arg_var, 0) + 1
                elif instr_type == inType.COMPARE:
                    tmp_dict_read[arg_var] = tmp_dict_read.get(arg_var, 0) + 1
                else:
                    continue
        return len(tmp_dict_read), len(tmp_dict_write)

    def GetInstructionType(self, instr_addr):
        insn = ida_ua.insn_t()
        inslen = ida_ua.decode_insn(insn, instr_addr)

        # TODO: something like `call $+5` should be exclusive
        if ida_idp.is_call_insn(insn):
            return inType.CALL
        # if the coderefs target is local and next instruction is_flow, then it's condition jump (not always true)
        # something like `jmp eax` is not available for conditional jump in x86 and x86/64
        refs = idautils.CodeRefsFrom(instr_addr, 0)
        refs = set(
            filter(
                lambda addr: addr >= self.function_start and addr <= self.
                function_end, refs))
        if refs:
            n_head = idc.next_head(instr_addr, self.function_end)
            if is_flow(ida_bytes.get_full_flags(n_head)):
                return inType.CONDITIONAL_BRANCH
            else:
                return inType.UNCONDITIONAL_BRACH
        if ida_idp.has_insn_feature(insn.itype, CF_CHG):
            return inType.ASSIGNMENT
        if ida_idp.has_insn_feature(insn.itype, CF_USE):
            return inType.COMPARE
        return inType.OTHERS


class Metrics:
    def __init__(self):
        self.metrics_mask = dict()
        self.total_loc_count = 0
        self.average_loc_count = 0.0
        self.total_bbl_count = 0
        self.total_func_count = 0
        self.total_condition_count = 0
        self.total_assign_count = 0
        self.R_total = 0.0
        self.CC_total = 0
        self.CL_total = 0
        self.ABC_total = 0
        self.Halstead_total = Halstead_metric()
        self.CC_modified_total = 0
        self.Pivovarsky_total = 0
        self.Harrison_total = 0.0
        self.boundary_values_total = 0.0
        self.span_metric_total = 0
        self.Oviedo_total = 0
        self.Chepin_total = 0
        self.global_vars_metric_total = 0.0
        self.Cocol_total = 0
        self.HenrynCafura_total = 0.0
        self.CardnGlass_total = 0.0
        self.functions = dict()

    def start_analysis(self, metrics_used):
        """
        The function starts static metrics analysis.
        @metrics_used - a dictionary of metrics used in the following format {metrics_list element:1 or 0}
        PTAL metrics_list global list and args_parser routine
        @return - None
        """
        self.metrics_mask = metrics_used
        # For each of the segments
        for seg_ea in idautils.Segments():
            # For each of the functions
            function_ea = seg_ea
            while function_ea != idaapi.BADADDR:
                function_name = idc.get_func_name(function_ea)
                # if already analyzed
                if self.functions.get(function_name, None) != None:
                    function_ea = idc.get_next_func(function_ea)
                    continue
                print(f"Analysing {function_name}@{hex(function_ea)}")
                try:
                    self.functions[function_name] = Metrics_function(
                        function_ea, self.metrics_mask)
                    self.functions[function_name].start_analysis()

                except Exception as e:
                    print(
                        f"Can't collect metric for function {function_name}@{hex(function_ea)}"
                    )
                    print(f"{e}")
                    print('Skip')
                    function_ea = idc.get_next_func(function_ea)
                    continue
                self.collect_total_metrics(function_name)
                function_ea = idc.get_next_func(function_ea)
        self.collect_final_metrics()

    def collect_final_metrics(self):
        ''' The routine collect some metrics that should be calculated after analysis
        '''
        if self.total_func_count > 0:
            self.average_loc_count = self.total_loc_count / self.total_func_count
        if self.metrics_mask["h"] == 1 or self.metrics_mask["cocol"] == 1:
            self.Halstead_total.calculate()
        if self.metrics_mask["global"] == 1:
            self.global_vars_metric_total = self.add_global_vars_metric()
        if self.metrics_mask["cocol"] == 1:
            self.Cocol_total += self.Halstead_total.B + self.CC_total + self.total_loc_count

    def collect_total_metrics(self, function_name):
        ''' The routine is used to add function measures to total metrics evaluation
        @function_name - name of function
        '''
        self.total_loc_count += self.functions[function_name].loc_count
        self.total_bbl_count += self.functions[function_name].bbl_count
        self.total_func_count += 1
        self.total_condition_count += self.functions[
            function_name].condition_count
        self.total_assign_count += self.functions[function_name].assign_count
        self.R_total += self.functions[function_name].R

        self.CC_modified_total += self.functions[function_name].CC_modified
        self.Pivovarsky_total += self.functions[function_name].Pivovarsky
        self.Harrison_total += self.functions[function_name].Harrison
        self.boundary_values_total += self.functions[
            function_name].boundary_values

        self.Halstead_total.n1 += self.functions[
            function_name].Halstead_basic.n1
        self.Halstead_total.n2 += self.functions[
            function_name].Halstead_basic.n2
        self.Halstead_total.N1 += self.functions[
            function_name].Halstead_basic.N1
        self.Halstead_total.N2 += self.functions[
            function_name].Halstead_basic.N2

        self.CC_total += self.functions[function_name].CC
        self.CL_total += self.functions[function_name].CL
        self.ABC_total += self.functions[function_name].ABC

        self.span_metric_total += self.functions[function_name].span_metric
        self.Oviedo_total += self.functions[function_name].Oviedo
        self.Chepin_total += self.functions[function_name].Chepin
        self.HenrynCafura_total += self.functions[function_name].HenrynCafura
        self.CardnGlass_total += self.functions[function_name].CardnGlass

        if self.metrics_mask["cocol"] == 1:
            self.functions[function_name].Cocol = self.functions[
                function_name].Halstead_basic.B + self.functions[
                    function_name].CC + self.functions[function_name].loc_count

    def add_global_vars_metric(self):
        '''
        The function calculates access count to global variables.
        @return - total access count
        '''

        total_metric_count = 0
        for function in self.functions:
            if len(global_vars_dict) > 0:
                self.functions[function].global_vars_metric = self.functions[
                    function].global_vars_access / len(global_vars_dict)
            total_metric_count += self.functions[function].global_vars_metric
        return total_metric_count


    def save_results_csv(self, name):
        if name == None:
            return 0

        f = open(name, 'w')
        header_functions = [
            'function name',
            'lines of code',
            'basic blocks (#)',
            'condition count (#)',
            'calls count (#)',
            'assignments count (#)',
            'cyclomatic complexity',
            'cyclomatic complexity modified',
            'jilb\'s metric',
            'abc',
            'r count',
            'halstead.b',
            'halstead.e',
            'halstead.d',
            'halstead.n*',
            'halstead.v',
            'halstead.N1',
            'halstead.N2',
            'halstead.n1',
            'halstead.n2',
            'pivovarsky',
            'harrison',
            'cocol metric',
            'boundary value',
            'span metric',
            'global vars metric',
            'oviedo metric',
            'chepin metric',
            'cardnglass metric',
            'henryncafura metric'
        ]
        # saving header
        f.write(','.join(header_functions))
        f.write('\n')
        # saving functions data
        for function in self.functions:
            cf = self.functions[function]
            f.write(str(function) + ",")
            f.write(("%.2f" % cf.loc_count) + ",")
            f.write(("%.2f" % cf.bbl_count) + ",")
            f.write(("%.2f" % cf.condition_count) + ",")
            f.write(("%.2f" % cf.calls_count) + ",")
            f.write(("%.2f" % cf.assign_count) + ",")
            f.write(("%.2f" % cf.CC) + ",")
            f.write(("%.2f" % cf.CC_modified) + ",")
            f.write(("%.2f" % cf.CL) + ",")
            f.write(("%.2f" % cf.ABC) + ",")
            f.write(("%.2f" % cf.R) + ",")
            f.write(("%.2f" % cf.Halstead_basic.B) + ",")
            f.write(("%.2f" % cf.Halstead_basic.E) + ",")
            f.write(("%.2f" % cf.Halstead_basic.D) + ",")
            f.write(("%.2f" % cf.Halstead_basic.Ni) + ",")
            f.write(("%.2f" % cf.Halstead_basic.V) + ",")
            f.write(("%.2f" % cf.Halstead_basic.N1) + ",")
            f.write(("%.2f" % cf.Halstead_basic.N2) + ",")
            f.write(("%.2f" % cf.Halstead_basic.n1) + ",")
            f.write(("%.2f" % cf.Halstead_basic.n2) + ",")
            f.write(("%.2f" % cf.Pivovarsky) + ",")
            f.write(("%.2f" % cf.Harrison) + ",")
            f.write(("%.2f" % cf.Cocol) + ",")
            f.write(("%.2f" % cf.boundary_values) + ",")
            f.write(("%.2f" % cf.span_metric) + ",")
            f.write(("%.2f" % cf.global_vars_metric) + ",")
            f.write(("%.2f" % cf.Oviedo) + ",")
            f.write(("%.2f" % cf.Chepin) + ",")
            f.write(("%.2f" % cf.CardnGlass) + ",")
            f.write(("%.2f" % cf.HenrynCafura) + "\n")
        f.close()

    def save_results(self, name):
        print('Average lines of code in a function:', self.average_loc_count)
        print('Total number of functions:', self.total_func_count)
        print('Total lines of code:', self.total_loc_count)
        print('Total bbl count:', self.total_bbl_count)
        print('Total assignments count:', self.total_assign_count)
        print('Total R count:', self.R_total)
        print('Total Cyclomatic complexity:', self.CC_total)
        print('Total Jilb\'s metric:', self.CL_total)
        print('Total ABC:', self.ABC_total)
        print('Halstead:', self.Halstead_total.B)
        print('Pivovarsky:', self.Pivovarsky_total)
        print('Harrison:', self.Harrison_total)
        print('Boundary value', self.boundary_values_total)
        print('Span metric', self.span_metric_total)
        print('Global var metric', self.global_vars_metric_total)
        print('Oviedo metric', self.Oviedo_total)
        print('Chepin metric', self.Chepin_total)
        print('Henry&Cafura metric', self.HenrynCafura_total)
        print('Cocol metric', self.Cocol_total)
        print('Card&Glass metric', self.CardnGlass_total)
        #Save in log file

        if name == None:
            return 0
        f = open(name, 'w')
        f.write('Average lines of code in a function: ' +
                str(self.average_loc_count) + "\n")
        f.write('Total number of functions: ' + str(self.total_func_count) +
                "\n")
        f.write('Total lines of code: ' + str(self.total_loc_count) + "\n")
        f.write('Total bbl count: ' + str(self.total_bbl_count) + "\n")
        f.write('Total assignments count: ' + str(self.total_assign_count) +
                "\n")
        f.write('Total R count: ' + str(self.R_total) + "\n")
        f.write('Total Cyclomatic complexity: ' + str(self.CC_total) + "\n")
        f.write('Total Jilb\'s metric: ' + str(self.CL_total) + "\n")
        f.write('Total ABC: ' + str(self.ABC_total) + "\n")
        f.write('Total Halstead:' + str(self.Halstead_total.B) + "\n")
        f.write('Total Pivovarsky: ' + str(self.Pivovarsky_total) + "\n")
        f.write('Total Harrison: ' + str(self.Harrison_total) + "\n")
        f.write('Total Boundary value: ' + str(self.boundary_values_total) +
                "\n")
        f.write('Total Span metric: ' + str(self.span_metric_total) + "\n")
        f.write('Total Oviedo metric: ' + str(self.Oviedo_total) + "\n")
        f.write('Total Chepin metric: ' + str(self.Chepin_total) + "\n")
        f.write('Henry&Cafura metric: ' + str(self.HenrynCafura_total) + "\n")
        f.write('Cocol metric: ' + str(self.Cocol_total) + "\n")
        f.write('CardnGlass metric: ' + str(self.CardnGlass_total) + "\n")
        for function in self.functions:
            f.write(str(function) + "\n")
            f.write('  Lines of code in the function: ' +
                    str(self.functions[function].loc_count) + "\n")
            f.write('  Bbls count: ' +
                    str(self.functions[function].bbl_count) + "\n")
            f.write('  Condition count: ' +
                    str(self.functions[function].condition_count) + "\n")
            f.write('  Calls count: ' +
                    str(self.functions[function].calls_count) + "\n")
            f.write('  Assignments count: ' +
                    str(self.functions[function].assign_count) + "\n")
            f.write('  Cyclomatic complexity: ' +
                    str(self.functions[function].CC) + "\n")
            f.write('  Cyclomatic complexity modified: ' +
                    str(self.functions[function].CC_modified) + "\n")
            f.write('  Jilb\'s metric: ' + str(self.functions[function].CL) +
                    "\n")
            f.write('  ABC: ' + str(self.functions[function].ABC) + "\n")
            f.write('  R count: ' + str(self.functions[function].R) + "\n")

            f.write('    Halstead.B: ' +
                    str(self.functions[function].Halstead_basic.B) + "\n")
            f.write('    Halstead.E: ' +
                    str(self.functions[function].Halstead_basic.E) + "\n")
            f.write('    Halstead.D: ' +
                    str(self.functions[function].Halstead_basic.D) + "\n")
            f.write('    Halstead.N*: ' +
                    str(self.functions[function].Halstead_basic.Ni) + "\n")
            f.write('    Halstead.V: ' +
                    str(self.functions[function].Halstead_basic.V) + "\n")
            f.write('    Halstead.N1: ' +
                    str(self.functions[function].Halstead_basic.N1) + "\n")
            f.write('    Halstead.N2: ' +
                    str(self.functions[function].Halstead_basic.N2) + "\n")
            f.write('    Halstead.n1: ' +
                    str(self.functions[function].Halstead_basic.n1) + "\n")
            f.write('    Halstead.n2: ' +
                    str(self.functions[function].Halstead_basic.n2) + "\n")

            f.write('  Pivovarsky: ' +
                    str(self.functions[function].Pivovarsky) + "\n")
            f.write('  Harrison: ' + str(self.functions[function].Harrison) +
                    "\n")
            f.write('  Cocol metric' + str(self.functions[function].Cocol) +
                    "\n")

            f.write('  Boundary value: ' +
                    str(self.functions[function].boundary_values) + "\n")
            f.write('  Span metric: ' +
                    str(self.functions[function].span_metric) + "\n")
            f.write('  Global vars metric:' +
                    str(self.functions[function].global_vars_metric) + "\n")
            f.write('  Oviedo metric: ' +
                    str(self.functions[function].Oviedo) + "\n")
            f.write('  Chepin metric: ' +
                    str(self.functions[function].Chepin) + "\n")
            f.write('  CardnGlass metric: ' +
                    str(self.functions[function].CardnGlass) + "\n")
            f.write('  Henry&Cafura metric: ' +
                    str(self.functions[function].HenrynCafura) + "\n")
        f.close()


def init_analysis(metrics_used):
    metrics_total = Metrics()
    metrics_total.start_analysis(metrics_used)  # 64bits IDA will stuck here
    current_time = strftime("%Y-%m-%d_%H-%M-%S")
    analyzed_file = ida_nalt.get_root_filename()
    analyzed_file = analyzed_file.replace(".", "_")
    extension = ".txt"
    if CSV:
        extension = ".csv"

    mask = analyzed_file + "_" + current_time + extension
    name = ida_kernwin.ask_file(1, mask, "Where to save metrics ?")
    if CSV:
        metrics_total.save_results_csv(name)
    else:
        metrics_total.save_results(name)
    return 0


class UI:
    def __init__(self, callback):
        self.metrics_used = dict()
        self.panel = QWidget()
        self.panel.setWindowTitle("Select metrics to calculate")
        self.panel.setLayout(QVBoxLayout())
        self.chks = []
        self.callback = callback
        groupbox = QGroupBox('metrics')
        groupbox.setLayout(QHBoxLayout())
        self.panel.layout().addWidget(groupbox)
        for col in range(len(metrics_list) // 5):
            col_layout = QVBoxLayout()
            for i in range(5):
                chk = QCheckBox(metrics_names[col * 5 + i])
                self.chks.append(chk)
                chk.setChecked(True)
                col_layout.addWidget(chk)
            groupbox.layout().addLayout(col_layout)
        button = QPushButton('Confirm')
        button.clicked.connect(self.GetUserChoice)
        self.panel.layout().addWidget(button)
        self.panel.show()

    def GetUserChoice(self):
        ''' The routine parses user choice and than calls callback function
        @ callback - callback function
        '''
        #parse user choice
        for iter, i in enumerate(metrics_list):
            self.metrics_used[i] = (
                self.chks[iter].checkState() == QtCore.Qt.Checked)
        self.callback(self.metrics_used)
        self.panel.close()


class debug:
    def list_type(ea):
        """
        return the list of type of instructions in a function for debugging
        example usage:
        it_list = list_type(0x187A0)
        """
        f = ida_funcs.get_func(ea)
        adr = f.start_ea
        ins = []
        while adr < f.end_ea:
            ins.append((self.GetInstructionType(adr), adr))
            adr = idc.next_head(adr)
        return ins


if __name__ == "__main__":
    ida_auto.auto_wait()  #wait while ida finish analysis
    if not idaapi.cvar.batch:
        from PyQt5.QtWidgets import QWidget, QGroupBox, QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QPushButton
        from PyQt5.QtWidgets import QMainWindow, QFileDialog, QDialog, QLineEdit, QMessageBox, QAction, QMenu, QApplication, QLabel
        from PyQt5 import QtCore, QtGui, QtWidgets
        ui = UI(init_analysis)
    else:  #hidden mode
        metrics_mask = dict()
        # calculate all metrics
        for i in metrics_list:
            metrics_mask[i] = 1

        metrics_total = Metrics()
        metrics_total.start_analysis(metrics_mask)
        current_time = strftime("%Y-%m-%d_%H-%M-%S")
        analyzed_file = ida_nalt.get_root_filename()
        analyzed_file = analyzed_file.replace(".", "_")
        file_name = os.getcwd() + "/" + analyzed_file + "_" + current_time
        if CSV:
            metrics_total.save_results_csv(file_name + ".csv")
        else:
            metrics_total.save_results(file_name + ".txt")
        idc.qexit(0)
