# RTED - Robust Tree Edit Distance
#
# This module implements the RTED algorithm for computing the tree edit 
# distance between two trees. It is as specified in the paper:
# "RTED: A Robust Algorithm for the Tree Edit Distance" by Pawlik & Augsten
#  https://www.vldb.org/pvldb/vol5/p334_mateuszpawlik_vldb2012.pdf
#
# The algorithm is optimized by using a heavy path decomposition of the tree.
# The heavy path is the path from the root to the child with the largest subtree.
# The algorithm recursively compares the heavy paths and the remaining children.
# The tree edit distance is the minimum cost of transforming the source tree into 
# the target tree.
#
# For more information, see the paper.
#

from lxml import etree
from typing import List, Tuple, Mapping, Optional, Literal
from enum import Enum
from dataclasses import dataclass
from lagasafn.pathing import make_xpath_from_node

class EditType(Enum):
    # Represents the type of edit operation in the tree edit script.
    # The edit operation is one of:
    #   - Insert: Insert a node into the tree.
    #   - Delete: Delete a node from the tree.
    #   - Update: Update the value of a node in the tree.
    #
    insert          = 1
    delete          = 2
    change          = 3
    change_attrib   = 4
    AddAttrib       = 5
    RemoveAttrib    = 6
    ChangeText      = 7
    ChangeTagType   = 8
    insert_b        = 10
    delete_b        = 20


@dataclass
class EditOperation:
    # Represents an edit operation in the tree edit script.
    # 
    # The source is the source node.
    # The target is the target node.
    #
    edit_type: EditType
    cost: int
    source: etree.Element
    target: etree.Element
    xpath: str = ""
    insertmode: Literal["explicit", "child", "after", "before"] = "explicit"

    def __str__(self):
        return f"[{self.edit_type}@{self.xpath}] {self.source} -> {self.target}"

SubtreeSizeMap = Mapping[etree.Element, int]
PathTable = Mapping[etree.Element, etree.Element]
TreeEditScript = List[EditOperation]

def compute_subtree_size(node: etree.Element, size_map: SubtreeSizeMap) -> int:
    # Computes the size of the subtree rooted at the given node.
    # The size is the number of nodes in the subtree, including the 
    # root and all children.
    # 
    # The computed sizes are stored in the size_map.
    #

    size = 1
    for child in node.getchildren():
        size += compute_subtree_size(child, size_map)

    size_map[node] = size
    return size

def compute_heavy_path(node: etree.Element, sizes: SubtreeSizeMap, paths: PathTable):
    # Computes the heavy path of the subtree rooted at the given node.
    # The heavy path is the child with the largest subtree.
    #
    # E.g., for the tree:
    # 
    #       A
    #      / \
    #     B   C
    #        / \
    #       D   E
    #      / \
    #     F   G
    #
    # The heavy path for A is C, for B is B, for C is D, for D is G, 
    #   for E is E, for F is F, and for G is G.
    # That is to say, the heaviest path in the tree is A-C-D-G.
    #
    # The function populates the paths table with the heavy paths.

    max_size = 0
    heavy_child = None

    for child in node:
        if sizes[child] > max_size:
            heavy_child = child
            max_size = sizes[child]
        
    paths[node] = heavy_child
    for child in node:
        compute_heavy_path(child, sizes, paths)


COMPARISONS = 0
MAX_DEPTH = 0

def compute_tree_edit_distance(
    source: Optional[etree.Element], 
    target: Optional[etree.Element],
    heavy: PathTable,
    depth: int = 0
) -> (int, TreeEditScript):

    global COMPARISONS
    global MAX_DEPTH

    COMPARISONS += 1
    MAX_DEPTH = max(MAX_DEPTH, depth)

    # print(f"Comparing {make_xpath_from_node(source)} -> {make_xpath_from_node(target)}")
    #
    # FIRST: We handle the situation where either source or target is None.
    #
    if source == None and target == None:
        return 0, [] # No cost if both nodes are none.

    # Source is empty, insert all nodes from target.
    if source == None:
        cost = 10
        for child in target.iter():
            cost += 1
        return cost, [EditOperation(EditType.insert_b, cost, None, target, make_xpath_from_node(target))]
    
    # Target is empty, delete all nodes from source.
    if target == None:
        cost = 10
        for child in source.iter():
            cost += 1
        return 1 + cost, [EditOperation(EditType.delete_b, cost, source, None, make_xpath_from_node(source))]

    #
    # Both source and target are non-empty.
    # So now we compute the cost of transforming source into target.
    #
    # CASE 2: Remove scenario
    #
    remove_cost = 20 + len(source.getchildren())
    for child in source.iter():
        remove_cost += 3
    remove_ops : List[EditOperation] = [
        EditOperation(EditType.delete, remove_cost, source, None, make_xpath_from_node(source))
    ]

    #
    # CASE 3: Insert scenario
    #
    insert_cost = 20 + len(target.getchildren())
    for child in target.iter():
        insert_cost += 3
    insert_ops : List[EditOperation] = [
        EditOperation(EditType.insert, insert_cost, None, target, make_xpath_from_node(target))
    ]

    #
    # CASE 4: Change scenario
    #
    change_ops : List[EditOperation] = []
    change_cost = 0

    if source.tag != target.tag:
        change_cost += 1
        #change_ops.append(EditOperation(EditType.ChangeTagType, source, target))

    if source.text != target.text:
        change_cost += 1
        #change_ops.append(EditOperation(EditType.ChangeText, source, target))

    # Each attrib change (add, remove, change) costs 1.
    source_attribs = set(source.attrib.keys())
    target_attribs = set(target.attrib.keys())
    change_cost += len(source_attribs.symmetric_difference(target_attribs))
    for key in source_attribs.intersection(target_attribs):
        if source.attrib[key] != target.attrib[key]:
            change_cost += 1

    if change_cost > 0:
        change_ops.append(EditOperation(EditType.change, change_cost, source, target, make_xpath_from_node(source)))

    # Compute the edit distance for the heavy paths.
    #heavy_source = heavy[source]
    #heavy_target = heavy[target]

    # The heavy cost is the cost of transforming the heavy paths.
    #heavy_cost, subscript = compute_tree_edit_distance(heavy_source, heavy_target, heavy, depth+1)

    #change_cost += heavy_cost
    #change_ops += subscript

    # Process remaining children (non-heavy paths). We do this by aggregating the remaining
    # children into two arrays, and then recursively comparing them. We sum these as "other_cost".
    other_source : List[etree.Element] = []
    for it in source.getchildren():
        #if it != heavy_source:
        other_source.append(it)

    other_target : List[etree.Element] = []
    for it in target.getchildren():
        # if it != heavy_target:
        other_target.append(it)

    # We'd normally just look at one pair at a time, but we really want to find the pair that has
    # the least cost. So we are going to try all combinations of source and target children
    # and find the edit set with the least cost:

    #strategies = []
    #for j in range(max(len(other_source), len(other_target))):
    #    strategy_ops  = []
    #    strategy_cost = 0
    #    maxarg = max(len(other_source), len(other_target))
    #    for i in range(maxarg):
    #        s_child = other_source[(j+i)%maxarg] if (j+i)%maxarg < len(other_source) else None
    #        t_child = other_target[i] if i < len(other_target) else None
    #        subcost, subscript = compute_tree_edit_distance(s_child, t_child, heavy, depth+1)
    #        strategy_cost += subcost
    #        strategy_ops  += subscript
#
    #    strategies.append((strategy_cost, strategy_ops))
    #
    #if len(strategies) > 0:
    #    # Now we have a list of strategies, we can pick the one with the least cost.
    #    scost, sops = min(strategies, key=lambda x: x[0])
    #    #print("Strategies: ", len(strategies))
    #    if depth == 1:
    #        print(f"Strategies: {len(strategies)} Best strategy: {sops}")
    #    change_cost += scost
    #    change_ops  += sops

    # This works but isn't ideal.
    other_cost : int = 0
    for i in range(max(len(other_source), len(other_target))):
        s_child = other_source[i] if i < len(other_source) else None
        t_child = other_target[i] if i < len(other_target) else None
        subcost, subscript = compute_tree_edit_distance(s_child, t_child, heavy, depth+1)
        other_cost += subcost
        change_ops += subscript

    change_cost += other_cost

    # The total cost is the sum of the change cost, the heavy cost, and the other cost.
    # total_cost = change_cost + heavy_cost + other_cost

    bestcost = min(remove_cost, insert_cost, change_cost)

    # print("---------------------------------")
    # print(f"      Depth: {depth}")
    # print(f"   Location: {make_xpath_from_node(source)} -> {make_xpath_from_node(target)}")
    # print(f"Remove cost: {remove_cost}; ops: {len(remove_ops)}.")
    # print(f"Insert cost: {insert_cost}; ops: {len(insert_ops)}.")
    # print(f"Change cost: {change_cost}; ops: {len(change_ops)}.")
    # print(f"       Best: {bestcost}.")
    # print("---------------------------------")

    if bestcost == remove_cost:
        return remove_cost, remove_ops
    
    if bestcost == insert_cost:
        return insert_cost, insert_ops

    # bestcost == change_cost
    return change_cost, change_ops


def rted(source: etree.Element, target: etree.Element) -> Tuple[int, TreeEditScript]:
    # Computes the tree edit distance between the source and target trees.
    # The function returns a tuple of the edit distance and the tree edit script.
    #
    # The tree edit script is a sequence of edit operations that transform the source tree
    # into the target tree.
    #
    # The function uses the RTED algorithm to compute the tree edit distance.
    #
    size_map : SubtreeSizeMap = {}
    compute_subtree_size(source, size_map)
    compute_subtree_size(target, size_map)

    heavy_paths : PathTable = {}
    compute_heavy_path(source, size_map, heavy_paths)
    compute_heavy_path(target, size_map, heavy_paths)

    distance, script = compute_tree_edit_distance(source, target, heavy_paths)

    return distance, script


def make_bill(tree1, tree2) -> str:
    cost, script = rted(tree1.getroot(), tree2.getroot())
    print("Comparisons: ", COMPARISONS)
    print("Max depth: ", MAX_DEPTH)
    print("<bill>")
    print(f"  <law codex=\"154a\" nr=\"{tree1.getroot().attrib["nr"]}\" year=\"{tree1.getroot().attrib["year"]}\" changes=\"{len(script)}\" cost=\"{cost}\">")
    for op in script:

        # v1 = etree.tostring(op.source, encoding="utf-8", pretty_print=True).decode("utf-8")
        # v2 = etree.tostring(op.target, encoding="utf-8", pretty_print=True).decode("utf-8")
        # if v1 == v2:
        #     print("Skipping identical nodes.")
        #     continue

        #print("\033[1;33m", end="")
        print(f"    <{op.edit_type.name} location=\"{op.xpath}\" cost=\"{op.cost}\">")
        #print("\033[0m")

        if op.source is not None:
            etree.indent(op.source, space="  ", level=4)
            # print("\033[1;34m", end="")
            print("      <source>")
            # print("\033[0m", end="")
            print(f"        {etree.tostring(op.source, encoding="utf-8", pretty_print=True).decode("utf-8")}")
            # print("\033[1;34m", end="")
            print("      </source>")
            # print("\033[0m", end="")

        if op.target is not None:
            etree.indent(op.target, space="  ", level=4)
            # print("\033[1;34m", end="")
            print("      <target>")
            # print("\033[0m", end="")
            print(f"        {etree.tostring(op.target, encoding="utf-8", pretty_print=True).decode("utf-8")}")
            # print("\033[1;34m", end="")
            print("      </target>")
            # print("\033[0m", end="")
        
        #print(f"\033[1;33m")
        print(f"    </{op.edit_type.name}>")
        #print("\033[1;0m")
    print("  </law>")
    print("</bill>")
