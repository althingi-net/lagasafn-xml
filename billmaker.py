from lagasafn import rted
from lxml import etree

import click



@click.command()
@click.argument('origin', type=click.Path(exists=True))
@click.argument('target', type=click.Path(exists=True))
@click.option('--output', '-o', default='output.xml', help='Output file')
def make_bill(origin, target, output):
    #file1 = "data/xml/154a/2003.83.xml"
    #file2 = "data/xml/154b/2003.83.xml"
    tree1 = etree.parse(origin)
    tree2 = etree.parse(target)

    bill = rted.make_bill(tree1, tree2)

    with open(output, 'wb') as f:
        f.write(etree.tostring(bill, pretty_print=True, encoding="utf-8"))
    print("Wrote bill to", output)

if __name__ == '__main__':
    make_bill()
