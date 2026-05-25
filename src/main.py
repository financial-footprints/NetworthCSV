from src.extractor import main as extractor_main
from src.cleanup import main as cleanup_main
# from src.parse import main as parse_main


def main():
    extractor_main()
    cleanup_main()
    # parse_main()


if __name__ == "__main__":
    main()
