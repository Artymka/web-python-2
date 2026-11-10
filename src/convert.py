import sys
import code128


def convert(inp: str, out: str) -> None:
    """Считывает текстовую строку из файла и сохраняет штрих-код."""
    with open(inp, "r", encoding="utf-8") as file:
        content = file.read().strip()
        code128.image(content).save(out, save_all=True)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
