import sys, time
import pytermgui as ptg

def macro_time(fmt: str) -> str:
    return time.strftime(fmt)

def main():
    with ptg.alt_buffer():
        root = ptg.Container(
            ptg.Label("[210 bold]This is a title"),
            ptg.Label(""),
            ptg.Label("[italic grey]This is some body text. It is very interesting."),
            ptg.Label(),
            ptg.Button("[red]Stop application!", onclick=lambda *_: sys.exit()),
            ptg.Button("[green]Do nothing"),
        )

        root.center().print()

        while True:
            root.handle_key(ptg.getch())
            root.print()
        
if __name__ == '__main__':
    main()