#!/usr/bin/env python3
import click
from lagasafn import rted
from lagasafn.utils import write_xml
from lxml import etree


@click.command()
@click.argument('origin', type=click.Path(exists=True))
@click.argument('target', type=click.Path(exists=True))
@click.option('--output', '-o', default='output.xml', help='Output file')
def make_bill(origin, target, output):
    tree1 = etree.parse(origin)
    tree2 = etree.parse(target)

    bill = rted.make_bill(tree1, tree2)

    write_xml(bill, output)
    print("Wrote bill to", output)

if __name__ == '__main__':
    make_bill()
