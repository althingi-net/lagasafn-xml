from lagasafn import rted
from lxml import etree

file1 = "data/xml/154a/2003.83.xml"
file2 = "data/xml/154b/2003.83.xml"

tree1 = etree.parse(file1)
tree2 = etree.parse(file2)

rted.make_bill(tree1, tree2)