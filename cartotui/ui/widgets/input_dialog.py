"""Small keyboard/mouse dialog hosted by the existing terminal application."""
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Float, HSplit
from prompt_toolkit.widgets import Button, Dialog, Label, TextArea


def ask_text(ctx, title, prompt, initial, accept):
    manager = ctx.manager
    if manager is None or manager._float_container is None:
        return
    app = get_app()
    previous = app.layout.current_window
    error = Label("")
    field = TextArea(text=initial, multiline=False)
    keys = KeyBindings()

    def close():
        manager._dialog_open = False
        floats = manager._float_container.floats
        if floating in floats:
            floats.remove(floating)
        try:
            app.layout.focus(previous)
        except ValueError:
            pass
        app.invalidate()

    def submit():
        try:
            accept(field.text)
        except (ValueError, OSError) as exc:
            error.text = str(exc)
            app.invalidate()
            return
        close()

    @keys.add("escape")
    def cancel(event):
        close()

    field.accept_handler = lambda buffer: submit()
    dialog = Dialog(title=title, body=HSplit([Label(prompt), field, error]),
                    buttons=[Button("Apply", handler=submit), Button("Cancel", handler=close)],
                    width=48, modal=False)
    floating = Float(content=HSplit([dialog], key_bindings=keys, modal=True))
    manager._dialog_open = True
    manager._float_container.floats.append(floating)
    app.layout.focus(field)
    app.invalidate()
