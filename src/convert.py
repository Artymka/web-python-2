import code128
import sys


def convert(inp: str, out: str):
    with open(inp) as i:
        content = i.read().strip()
        code128.image(content).save(out, save_all=True)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
