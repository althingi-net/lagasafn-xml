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
from typing import List, Tuple, Mapping, Optional
from enum import Enum
from dataclasses import dataclass

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


@dataclass
class EditOperation:
    # Represents an edit operation in the tree edit script.
    # 
    # The source is the source node.
    # The target is the target node.
    #
    edit_type: EditType
    source: etree.Element
    target: etree.Element

    def __str__(self):
        return f"[{self.edit_type}] {self.source} -> {self.target}"

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


def compute_tree_edit_distance(
    source: Optional[etree.Element], 
    target: Optional[etree.Element],
    heavy: PathTable,
) -> (int, TreeEditScript):

    #
    # FIRST: We handle the situation where either source or target is None.
    #
    if source == None and target == None:
        return 0, [] # No cost if both nodes are none.

    # TODO: The costing of this case is wrong
    # Source is empty, insert all nodes from target.
    if source == None:
        return 1 + len(target.getchildren()), [EditOperation(EditType.insert, None, target)]
    
    # TODO: The costing of this case is wrong
    # Target is empty, delete all nodes from source.
    if target == None:
        return 1 + len(source.getchildren()), [EditOperation(EditType.delete, source, None)]

    #
    # Both source and target are non-empty.
    # So now we compute the cost of transforming source into target.
    #
    # CASE 2: Remove scenario
    #
    # TODO: This cost is wrong
    remove_ops : List[EditOperation] = [
        EditOperation(EditType.delete, source, None)
    ]
    remove_cost = 1 + len(source.getchildren())
    for child in source.iter():
        remove_cost += 1

    #
    # CASE 3: Insert scenario
    #
    # TODO: This cost is wrong
    insert_ops : List[EditOperation] = [
        EditOperation(EditType.insert, None, target)
    ]
    insert_cost = 1 + len(target.getchildren())
    for child in target.iter():
        insert_cost += 1

    #
    # CASE 4: Change scenario
    #
    change_ops : List[EditOperation] = []
    change_cost = 0

    if source.tag != target.tag:
        change_cost += 1
        # change_ops.append(EditOperation(EditType.ChangeTagType, source, target))

    if source.text != target.text:
        change_cost += 1
        # change_ops.append(EditOperation(EditType.ChangeText, source, target))

    # Each attrib change (add, remove, change) costs 1.
    source_attribs = set(source.attrib.keys())
    target_attribs = set(target.attrib.keys())
    change_cost += len(source_attribs.symmetric_difference(target_attribs))
    for key in source_attribs.intersection(target_attribs):
        if source.attrib[key] != target.attrib[key]:
            change_cost += 1
    
    if change_cost > 0:
        change_ops.append(EditOperation(EditType.change, source, target))

    # Compute the edit distance for the heavy paths.
    heavy_source = heavy[source]
    heavy_target = heavy[target]

    # The heavy cost is the cost of transforming the heavy paths.
    heavy_cost, subscript = compute_tree_edit_distance(heavy_source, heavy_target, heavy)

    change_cost += heavy_cost
    change_ops += subscript

    # Process remaining children (non-heavy paths). We do this by aggregating the remaining
    # children into two arrays, and then recursively comparing them. We sum these as "other_cost".
    other_source : List[etree.Element] = []
    for it in source.getchildren():
        if it != heavy_source:
            other_source.append(it)

    other_target : List[etree.Element] = []
    for it in target.getchildren():
        if it != heavy_target:
            other_target.append(it)

    other_cost : int = 0
    for i in range(max(len(other_source), len(other_target))):
        s_child = other_source[i] if i < len(other_source) else None
        t_child = other_target[i] if i < len(other_target) else None
        subcost, subscript = compute_tree_edit_distance(s_child, t_child, heavy)
        other_cost += subcost
        change_ops += subscript

    change_cost += other_cost

    # The total cost is the sum of the change cost, the heavy cost, and the other cost.
    # total_cost = change_cost + heavy_cost + other_cost

    bestcost = min(remove_cost, insert_cost, change_cost)

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


if __name__ == "__main__":
    from lxml import etree
    file1 = "../data/xml/154a/2003.83.xml"
    file2 = "../data/xml/154b/2003.83.xml"

    tree1 = etree.parse(file1)
    tree2 = etree.parse(file2)

    distance, script = rted(tree1.getroot(), tree2.getroot())
    print("<bill>")
    print(f"  <law codex=\"154a\" nr=\"{tree1.getroot().attrib["nr"]}\" year=\"{tree1.getroot().attrib["year"]}\" changes=\"{distance}\">")
    for op in script:
        #print("\033[1;33m", end="")
        print(f"    <{op.edit_type.name}>")
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