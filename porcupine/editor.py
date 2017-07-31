"""The main Editor class is in this module."""

import functools
import logging
import os
import tkinter as tk
import traceback
import webbrowser

import pygments.styles

from porcupine import __doc__ as init_docstring
from porcupine import dialogs, settingdialog, tabs, utils
from porcupine.settings import config, InvalidValue


log = logging.getLogger(__name__)

__all__ = ['Editor']


def _create_welcome_msg(frame):
    description_lines = []
    for line in init_docstring.split('\n\n'):
        description_lines.append(' '.join(line.split()))

    # the texts will be packed closed to each other into this
    innerframe = tk.Frame(frame)
    innerframe.place(relx=0.5, rely=0.5, anchor='center')  # float in center

    titlelabel = tk.Label(innerframe, font='TkDefaultFont 16',
                          text="Welcome to Porcupine!")
    titlelabel.pack()
    desclabel = tk.Label(innerframe, font='TkDefaultFont 12',
                         text='\n\n'.join(description_lines))
    desclabel.pack()

    def resize(event):
        for label in [titlelabel, desclabel]:
            label['wraplength'] = event.width * 0.9    # small borders

    frame.bind('<Configure>', resize, add=True)


# See __main__.py for the code that actally runs this.
class Editor(tk.Frame):
    """The main class that takes care of menus, tabs and other things.

    The *destroy_callback* is called with no arguments when the user
    wants to close the whole editor. It does nothing by default.
    """

    def __init__(self, *args, destroy_callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.destroy_callback = destroy_callback

        self.tabmanager = tabs.TabManager(self)
        self.tabmanager.pack(fill='both', expand=True)
        _create_welcome_msg(self.tabmanager.no_tabs_frame)

        self.new_tab_hook = self.tabmanager.new_tab_hook
        self.tab_changed_hook = utils.ContextManagerHook(__name__)

        self.menubar = tk.Menu(tearoff=False)
        self._submenus = {}     # {(parentmenu, label): submenu, ...}
        self.get_menu("Help")   # see comments in get_menu()
        self._setup_menus()

        self.tabmanager.tab_changed_hook.connect(self._tab_changed)
        self._tab_context_manager = None
        self._tab_changed(None)

        for binding, callback in self.tabmanager.bindings:
            self.add_action(callback, binding=binding)

    def get_menu(self, label_path):
        """Return a submenu from the menubar.

        The submenu will be created if it doesn't exist already. The
        *label_path* should be a ``/``-separated string of menu labels;
        for example, ``'File/Stuff'`` is a Stuff submenu under the File
        menu.
        """
        current_menu = self.menubar
        for label in label_path.split('/'):
            try:
                current_menu = self._submenus[(current_menu, label)]
            except KeyError:
                submenu = tk.Menu(tearoff=False)
                if current_menu is self.menubar:
                    # the help menu is always last, like in most other programs
                    index = current_menu.index('end')
                    if index is None:
                        # there's nothing in the menu bar yet, we're
                        # adding the help menu now
                        index = 0
                    current_menu.insert_cascade(
                        index, label=label, menu=submenu)
                else:
                    current_menu.add_cascade(label=label, menu=submenu)

                self._submenus[(current_menu, label)] = submenu
                current_menu = submenu

        return current_menu

    def add_action(self, callback, menupath=None, accelerator=None,
                   binding=None, tabtypes=(None, tabs.Tab)):
        """Add a keyboard binding and/or a menu item.

        If *menupath* is given, it will be split by the last ``/``. The
        first part will be used to get a menu with :meth:`~get_menu`,
        and the end will be used as the text of the menu item.

        Keyboard shortcuts can be added too. If given, *accelerator*
        should be a user-readable string and *binding* should be a
        tkinter keyboard binding.

        If defined, the *tabtypes* argument should be an iterable of
        :class:`porcupine.tabs.Tab` subclasses that this item can work
        with. If you want to allow no tabs at all, add None to this
        list. The menuitem will be disabled and the binding won't do
        anything when the current tab is not of a compatible type.

        Example::

            def print_hello():
                print("hello")

            editor.add_action(print_hello, menupath="Hello/Hello World")
        """
        tabtypes = tuple((
            # isinstance(None, type(None)) is True
            type(None) if cls is None else cls
            for cls in tabtypes
        ))

        if menupath is not None:
            menupath, menulabel = menupath.rsplit('/', 1)
            menu = self.get_menu(menupath)
            menu.add_command(label=menulabel, command=callback,
                             accelerator=accelerator)
            menuindex = menu.index('end')

            def tab_changed(new_tab):
                if isinstance(new_tab, tabtypes):
                    menu.entryconfig(menuindex, state='normal')
                else:
                    menu.entryconfig(menuindex, state='disabled')

            tab_changed(self.tabmanager.current_tab)
            self.tabmanager.tab_changed_hook.connect(tab_changed)

        if binding is not None:
            # TODO: check if it's already bound
            def bind_callback(event):
                if isinstance(self.tabmanager.current_tab, tabtypes):
                    callback()
                    # try to allow binding keys that are used for other
                    # things by default, see also add_bindings()
                    return 'break'

            self.bind(binding, bind_callback)

    def _setup_menus(self):
        add = self.add_action       # less lines of code and useless typing
        add(self.new_file, "File/New File", "Ctrl+N", '<Control-n>')
        add(self.open_files, "File/Open", "Ctrl+O", '<Control-o>')
        add((lambda: self.tabmanager.current_tab.save()),
            "File/Save", "Ctrl+S", '<Control-s>', [tabs.FileTab])
        add((lambda: self.tabmanager.current_tab.save_as()),
            "File/Save As...", "Ctrl+Shift+S", '<Control-S>', [tabs.FileTab])
        self.get_menu("File").add_separator()
        # TODO: rename to 'File/Quit' when possible?
        add(self._close_tab_or_quit, "File/Close", "Ctrl+W", '<Control-w>')

        def textmethod(attribute):
            def result():
                textwidget = self.tabmanager.current_tab.textwidget
                method = getattr(textwidget, attribute)
                method()
            return result

        # FIXME: bind these in a text widget only, not globally
        add(textmethod('undo'), "Edit/Undo", "Ctrl+Z", '<Control-z>',
            [tabs.FileTab])
        add(textmethod('redo'), "Edit/Redo", "Ctrl+Y", '<Control-y>',
            [tabs.FileTab])
        add(textmethod('cut'), "Edit/Cut", "Ctrl+X", '<Control-x>',
            [tabs.FileTab])
        add(textmethod('copy'), "Edit/Copy", "Ctrl+C", '<Control-c>',
            [tabs.FileTab])
        add(textmethod('paste'), "Edit/Paste", "Ctrl+V", '<Control-v>',
            [tabs.FileTab])
        add(textmethod('select_all'), "Edit/Select All",
            "Ctrl+A", '<Control-a>', [tabs.FileTab])
        self.get_menu("Edit").add_separator()
        # TODO: make this a plugin!
        add((lambda: self.tabmanager.current_tab.find()),
            "Edit/Find and Replace", "Ctrl+F", '<Control-f>', [tabs.FileTab])

        # TODO: make sure that things added by plugins appear here,
        # before the separator and "Porcupine Settings" (see get_menu)
        self.get_menu("Edit").add_separator()
        add(settingdialog.show, "Edit/Porcupine Settings...")

        self.get_menu("Color Themes")   # this goes between Edit and View

        # the font size stuff are bound in textwidget.MainText
        add((lambda: self.tabmanager.current_tab.textwidget.on_wheel('up')),
            "View/Bigger Font", "Ctrl+Plus", tabtypes=[tabs.FileTab])
        add((lambda: self.tabmanager.current_tab.textwidget.on_wheel('down')),
            "View/Smaller Font", "Ctrl+Minus", tabtypes=[tabs.FileTab])
        add((lambda: self.tabmanager.current_tab.textwidget.on_wheel('reset')),
            "View/Reset Font Size", "Ctrl+Zero", tabtypes=[tabs.FileTab])
        self.get_menu("View").add_separator()

        def link(menupath, url):
            callback = functools.partial(webbrowser.open, url)
            self.add_action(callback, menupath)

        # TODO: porcupine starring button
        link("Help/Free help chat",
             "http://webchat.freenode.net/?channels=%23%23learnpython")
        link("Help/My Python tutorial",
             "https://github.com/Akuli/python-tutorial/blob/master/README.md")
        link("Help/Official Python documentation", "https://docs.python.org/")
        self.get_menu("Help").add_separator()
        link("Help/Porcupine Wiki", "https://github.com/Akuli/porcupine/wiki")
        link("Help/Report a problem or request a feature",
             "https://github.com/Akuli/porcupine/issues/new")
        link("Help/Read Porcupine's code",
             "https://github.com/Akuli/porcupine/tree/master/porcupine")

        stylenamevar = tk.StringVar()
        for name in sorted(pygments.styles.get_all_styles()):
            # the command runs config['Editing', 'pygments_style'] = name
            options = {
                'label': name.replace('-', ' ').replace('_', ' ').title(),
                'value': name, 'variable': stylenamevar,
                'command': functools.partial(
                    config.__setitem__, ('Editing', 'pygments_style'), name),
            }

            style = pygments.styles.get_style_by_name(name)
            bg = style.background_color

            # styles have a style_for_token() method, but only iterating
            # is documented :( http://pygments.org/docs/formatterdevelopment/
            # i'm using iter() to make sure that dict() really treats
            # the style as an iterable of pairs instead of some other
            # metaprogramming fanciness
            fg = None
            style_infos = dict(iter(style))
            for token in [pygments.token.String, pygments.token.Text]:
                if style_infos[token]['color'] is not None:
                    fg = '#' + style_infos[token]['color']
                    break
            if fg is None:
                # do like textwidget.ThemedText._set_style does
                fg = (getattr(style, 'default_style', '')
                      or utils.invert_color(bg))

            options['foreground'] = options['activebackground'] = fg
            options['background'] = options['activeforeground'] = bg

            self.get_menu("Color Themes").add_radiobutton(**options)

        config.connect('Editing', 'pygments_style', stylenamevar.set,
                       run_now=True)

    def _tab_changed(self, new_tab):
        # accessing __enter__ and __exit__ like this is lol, it feels
        # kind of evil >xD MUHAHAHAHAHAA!!!
        if self._tab_context_manager is not None:
            # not running this for the first time
            self._tab_context_manager.__exit__(None, None, None)

        self._tab_context_manager = self.tab_changed_hook.run(new_tab)
        self._tab_context_manager.__enter__()

    def new_file(self):
        """Add a new :class:`porcupine.tabs.FileTab` to the editor."""
        tab = tabs.FileTab(self.tabmanager)
        utils.copy_bindings(self, tab.textwidget)
        self.tabmanager.add_tab(tab)

    def open_files(self):
        """Ask the user to choose files and open them."""
        defaultdir = None
        if isinstance(self.tabmanager.current_tab, tabs.FileTab):
            path = self.tabmanager.current_tab.path
            if path is not None:
                defaultdir = os.path.dirname(path)

        for path in dialogs.open_files(defaultdir):
            try:
                encoding = config["Files", "encoding"]
                with open(path, encoding=encoding) as f:
                    tab = tabs.FileTab(self.tabmanager, f.read(), path=path)
            except (OSError, UnicodeError) as e:
                log.exception("opening '%s' failed", path)
                utils.errordialog(type(e).__name__, "Opening failed!",
                                  traceback.format_exc())
                continue
            utils.copy_bindings(self, tab.textwidget)
            self.tabmanager.add_tab(tab, make_current=True)

    def _close_tab_or_quit(self):
        tab = self.tabmanager.current_tab
        if tab is None:
            # no more tabs
            self.do_quit()
        elif tab.can_be_closed():
            tab.close()

    def do_quit(self):
        """Make sure that all tabs can be closed and stop the main loop."""
        for tab in self.tabmanager.tabs:
            if not tab.can_be_closed():
                return
            # the tabs must not be closed here, otherwise some of them
            # are closed if not all tabs can be closed

        # this also invokes self.tabmanager.destroy(), and that closes
        # all open tabs
        self.destroy()
        if self.destroy_callback is not None:
            self.destroy_callback()
