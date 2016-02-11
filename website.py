#!/use/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import sys
import json
import argparse

from flask import Flask, Blueprint, render_template
from flask import abort
from flask.helpers import send_from_directory
from flask_frozen import Freezer
from flask.ext.markdown import Markdown

from colorama import Fore

NEAR_COMPLETE = 1
INCOMPLETE = 2
NEAR_MISSING = 3
MISSING = 4
EXTRA = 5

formularprojekt = Blueprint('formularprojekt', __name__)
forms = {}
_translations = {}
translations = {}
stats = {}


def load_data(top):
    for dirpath, dirnames, filenames in os.walk(top):
        for filename in filenames:
            form_id = os.path.basename(dirpath)
            path = os.path.join(dirpath, filename)

            if filename.endswith('.json'):
                lang_id = filename[:-5]

                if lang_id == 'form':
                    with open(path) as fh:
                        form = json.load(fh)

                        keys = set([r['content'] for r in form['rows']])
                        if '' in keys:
                            keys.remove('')
                        form['keys'] = keys

                        forms[form_id] = form
                else:
                    if lang_id not in _translations:
                        _translations[lang_id] = {}
                    if lang_id != 'de' or form_id == 'meta':
                        with open(path) as fh:
                            _translations[lang_id][form_id] = json.load(fh)

    for lang_id in _translations:
        stats[lang_id] = {}

        for form_id in list(forms.keys()) + ['meta']:
            if form_id == 'meta':
                keys = set(_translations['en']['meta'].keys())
            else:
                keys = forms[form_id]['keys']

            n = len(keys)

            if form_id in _translations[lang_id]:
                translation = _translations[lang_id][form_id]
                tkeys = set(translation.keys())

                data = {
                    'translated': tkeys.intersection(keys),
                    'untranslated': keys.difference(tkeys),
                    'extra': tkeys.difference(keys),
                }
            else:
                data = {
                    'translated': [],
                    'untranslated': keys,
                    'extra': [],
                }

            if len(data['extra']) > 0:
                data['style'] = EXTRA
            elif len(data['translated']) == 0:
                data['style'] = MISSING
            elif len(data['translated']) < n * 0.2:
                data['style'] = NEAR_MISSING
            elif len(data['translated']) < n * 0.8:
                data['style'] = INCOMPLETE
            elif len(data['translated']) < n:
                data['style'] = NEAR_COMPLETE
            else:
                data['style'] = None

            stats[lang_id][form_id] = data

    for lang_id in _translations:
        if 'meta' in _translations[lang_id]:
            translations[lang_id] = {}
            translations[lang_id]['meta'] = _translations[lang_id]['meta']

            for form_id, translation in _translations[lang_id].items():
                if form_id in forms:
                    form = forms[form_id]
                    if len(translation) >= 0.8 * len(form['keys']):
                        translations[lang_id][form_id] = translation


def log(s, style=None, indent=0):
    if sys.stdout.isatty():
        reset = Fore.RESET

        if style == EXTRA:
            color = Fore.RED
        elif style == MISSING:
            color = Fore.MAGENTA
        elif style == NEAR_MISSING:
            color = Fore.YELLOW
        elif style == INCOMPLETE:
            color = Fore.CYAN
        elif style == NEAR_COMPLETE:
            color = Fore.GREEN
        else:
            color = ''
    else:
        reset = ''
        color = ''

    print(' ' * indent + color + s + reset)


def _form_stats(form_id, langs, verbose):
    print(form_id)

    for lang_id in langs:
        translated = stats[lang_id][form_id]['translated']
        untranslated = stats[lang_id][form_id]['untranslated']
        extra = stats[lang_id][form_id]['extra']
        style = stats[lang_id][form_id]['style']

        n = len(translated) + len(untranslated)
        s = '%s: %i/%i/%i' % (lang_id, len(translated), n, len(extra))
        log(s, style, 2)

        if verbose:
            for s in untranslated:
                log(s, MISSING, 4)
            for s in extra:
                log(s, EXTRA, 4)

    print('')


def print_stats(form_id=None, lang_id=None, verbose=False):
    if lang_id is None:
        langs = list(stats.keys())
        langs.remove('de')
        langs.sort()
    else:
        langs = [lang_id]

    if form_id is None:
        _form_stats('meta', langs, verbose)
        for form_id in sorted(forms.keys()):
            _form_stats(form_id, langs, verbose)
    else:
        _form_stats(form_id, langs, verbose)


@formularprojekt.app_template_filter('translate')
def translate_filter(s, lang_id, form_id, default=None):
    try:
        return translations[lang_id][form_id][s]
    except KeyError:
        pass

    if default is None:
        if form_id == 'meta':
            try:
                return translations['de'][form_id][s]
            except:
                pass

        return s
    else:
        return default


@formularprojekt.app_template_filter('text_direction')
def text_direction_filter(lang_id):
    try:
        return translations[lang_id]['meta']['direction']
    except KeyError:
        return 'auto'


@formularprojekt.route('/')
def index_route():
    return render_template(
        'index.html',
        translations=translations,
        lang_id='de')


@formularprojekt.route('/<lang_id>/')
def language_route(lang_id):
    if lang_id not in translations:
        abort(404)

    return render_template(
        'language.html',
        translations=translations,
        forms=forms,
        lang_id=lang_id,
        any_translations=len(translations[lang_id]) > 1)  # only meta


@formularprojekt.route('/<lang_id>/<form_id>/')
def translation_route(lang_id, form_id):
    available_languages = [l for l in translations
        if form_id in translations[l]]

    if lang_id not in translations:
        abort(404)
    if form_id not in forms:
        abort(404)
    if form_id not in translations[lang_id]:
        abort(404)

    return render_template(
        'translation.html',
        forms=forms,
        lang_id=lang_id,
        form_id=form_id,
        available_languages=available_languages)


@formularprojekt.route('/<lang_id>/<form_id>/print/')
def print_route(lang_id, form_id):
    if lang_id not in translations:
        abort(404)
    if form_id not in forms:
        abort(404)
    if form_id not in translations[lang_id]:
        abort(404)

    page_n = max((row['page'] for row in forms[form_id]['rows']))
    pages = []
    bg_template = 'static/forms/%s/bg-%i.svg'
    for i in range(page_n + 1):
        pages.append({
            'bg': os.path.exists(bg_template % (form_id, i)),
            'rows': []
        })
    for row in forms[form_id]['rows']:
        n = int(row['page'])
        pages[n]['rows'].append(row)

    return render_template(
        'print.html',
        forms=forms,
        pages=pages,
        lang_id=lang_id,
        form_id=form_id)


@formularprojekt.route('/stats/')
def stats_route():
    langs = list(stats.keys())
    langs.remove('de')
    langs.sort()

    return render_template(
        'stats.html',
        stats=stats,
        langs=langs,
        forms=forms)


def send_annotator_file(filename='index.html'):
    return send_from_directory('annotator', filename)


def send_data_file(filename):
    return send_from_directory('data', filename)


def add_annotator_rules(app):
    app.add_url_rule(
        '/annotator/',
        endpoint='annotator',
        view_func=send_annotator_file)
    app.add_url_rule(
        '/annotator/<path:filename>',
        endpoint='annotator_static',
        view_func=send_annotator_file)
    app.add_url_rule(
        '/data/<path:filename>',
        endpoint='data',
        view_func=send_data_file)


def register_annotator_files():
    yield '/annotator/annotator.css'
    yield '/annotator/annotator.js'
    yield '/annotator/template.html'
    yield '/annotator/bower_components/muu/dist/muu.min.js'
    yield '/annotator/bower_components/promise-xhr/promise-xhr.js'
    yield '/annotator/bower_components/markdown-it/dist/markdown-it.min.js'

    for form_id in forms:
        for filename in os.listdir(os.path.join('data', form_id)):
            yield '/data/%s/%s' % (form_id, filename)


def create_app(settings=None):
    app = Flask(__name__)
    app.config.from_object(settings)
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.register_blueprint(formularprojekt)
    Markdown(app)
    return app


def create_freezer(app):
    app.config.update({
        'FREEZER_BASE_URL': '/formularprojekt/',
        'FREEZER_REMOVE_EXTRA_FILES': True,
    })
    return Freezer(app)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true', dest='DEBUG')
    subparsers = parser.add_subparsers(title='commands')

    parser_build = subparsers.add_parser('build', help='generate static HTML')
    parser_build.set_defaults(cmd='build')

    parser_stats = subparsers.add_parser('stats', help='validate translations')
    parser_stats.add_argument('--verbose', '-v', action='store_true')
    parser_stats.add_argument('--lang', '-l')
    parser_stats.add_argument('form', nargs='?')
    parser_stats.set_defaults(cmd='stats')

    parser_serve = subparsers.add_parser('serve', help='run a test server')
    parser_serve.add_argument('--port', '-p', type=int, default=8000)
    parser_serve.set_defaults(cmd='serve')

    return parser.parse_args(argv)


def main():  # pragma: no cover
    args = parse_args()
    load_data('data')

    app = create_app(args)
    add_annotator_rules(app)

    if args.cmd == 'serve':
        app.run(port=args.port)
    elif args.cmd == 'stats':
        print_stats(args.form, args.lang, args.verbose)
    else:
        freezer = create_freezer(app)
        freezer.register_generator(register_annotator_files)
        freezer.freeze()


if __name__ == '__main__':
    sys.exit(main())
