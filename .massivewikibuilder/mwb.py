#!/usr/bin/env python

# Massive Wiki Builder v1.7.0 - https://github.com/peterkaminski/massivewikibuilder

# set up logging
import logging, os
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'WARNING').upper())

# python libraries
import argparse
import json
import re
import shutil
import sys
import traceback

import datetime
from pathlib import Path

import yaml
import jinja2

from markdown import Markdown
sys.path.append('./mwb_wikilink_plus/')
from mwb_wikilink_plus.mwb_wikilink_plus import WikiLinkPlusExtension

# set up argparse
def init_argparse():
    parser = argparse.ArgumentParser(description='Generate HTML pages from Markdown wiki pages.')
    parser.add_argument('--config', '-c', required=True, help='path to YAML config file')
    parser.add_argument('--output', '-o', required=True, help='directory for output')
    parser.add_argument('--templates', '-t', required=True, help='directory for HTML templates')
    parser.add_argument('--wiki', '-w', required=True, help='directory containing wiki files (Markdown + other)')
    return parser

wikifiles = {}

def mwb_build_wikilink(path, base, end, url_whitespace, url_case):
    logging.debug("1 mwb_build_wikilink: path: ", path)
    path_name = Path(path).name
    wikilink = Path(path_name).as_posix()  # use path_name if no wikipath
    if path_name in wikifiles.keys():
        wikipath = wikifiles[path_name]
        logging.debug("2 mwb_build_wikilink: wikipath: ", wikipath)
        if wikipath.endswith('.md'):
            wikilink = Path(wikipath).with_suffix('.html').as_posix()
        else:
            wikilink = Path(wikipath).as_posix()
    logging.debug("3 mwb_build_wikilink return: ", wikilink)
    return wikilink

# set up markdown
markdown_configs = {
    'mwb_wikilink_plus': {
        'base_url': '',
        'end_url': '.html',
        'url_whitespace': '_',
        'build_url': mwb_build_wikilink,
    },
}
markdown_extensions = [
    'footnotes',
    'tables',
    WikiLinkPlusExtension(markdown_configs['mwb_wikilink_plus']),
]
markdown = Markdown(output_format="html5", extensions=markdown_extensions)

# set up a Jinja2 environment
def jinja2_environment(path_to_templates):
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(path_to_templates)
    )

# load config file
def load_config(path):
    with open(path) as infile:
        return yaml.safe_load(infile)

# scrub wiki path to handle ' ', '_', '?', and '#' characters in wiki page names
# change ' ', ?', and '#' to '_', because they're inconvenient in URLs
def scrub_path(filepath):
    return re.sub(r'([ _?\#]+)', '_', filepath)

# take a path object pointing to a Markdown file
# return Markdown (as string) and YAML front matter (as dict)
# for YAML, {} = no front matter, False = YAML syntax error
def read_markdown_and_front_matter(path):
    with path.open() as infile:
        lines = infile.readlines()
    # take care to look exactly for two `---` lines with valid YAML in between
    if lines and re.match(r'^---$',lines[0]):
        count = 0
        found_front_matter_end = False
        for line in lines[1:]:
            count += 1
            if re.match(r'^---$',line):
                found_front_matter_end = True
                break;
        if found_front_matter_end:
            try:
                front_matter = yaml.safe_load(''.join(lines[1:count]))
            except yaml.parser.ParserError:
                # return Markdown + False (YAML syntax error)
                return ''.join(lines), False
            # return Markdown + front_matter
            return ''.join(lines[count+1:]), front_matter
    # return Markdown + empty dict
    return ''.join(lines), {}

# read and convert Sidebar markdown to HTML
def sidebar_convert_markdown(path):
    if path.exists():
        markdown_text, front_matter = read_markdown_and_front_matter(path)
    else:
        markdown_text = ''
    return markdown.convert(markdown_text)

# handle datetime.date serialization for json.dumps()
def datetime_date_serializer(o):
    if isinstance(o, datetime.date):
        return o.isoformat()

def main():
    logging.debug("Initializing")

    argparser = init_argparse();
    args = argparser.parse_args();
    logging.debug(f"args: {args}")

    # get configuration
    config = load_config(args.config)

    # remember paths
    dir_output = os.path.abspath(args.output)
    dir_templates = os.path.abspath(args.templates)
    dir_wiki = os.path.abspath(args.wiki)

    # get a Jinja2 environment
    j = jinja2_environment(dir_templates)

    # render the wiki
    try:
        # remove existing output directory and recreate
        logging.debug("remove existing output directory and recreate")
        shutil.rmtree(dir_output, ignore_errors=True)
        os.mkdir(dir_output)

        # generate dict of filenames and their wikipaths
        for root,dirs,files in os.walk(dir_wiki):
            dirs[:]=[d for d in dirs if not d.startswith('.')]
            files=[f for f in files if not f.startswith('.')]
            readable_path = root[len(dir_wiki):]
            path = scrub_path(readable_path)
            for file in files:
                if file in ['netlify.toml']:
                    continue
                clean_name = scrub_path(file)
                if '.md' == Path(file).suffix.lower():
                    wikifiles[Path(file).stem] = (Path(path) / clean_name).as_posix()
                else:
                    wikifiles[Path(file).name] = (Path(path) / clean_name).as_posix()
        logging.debug("wikifiles: ", wikifiles)
        # copy wiki to output; render .md files to HTML
        logging.debug("copy wiki to output; render .md files to HTML")
        all_pages = []
        page = j.get_template('page.html')
        build_time = datetime.datetime.now(datetime.timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
        if 'sidebar' in config:
            sidebar_body = sidebar_convert_markdown(Path(dir_wiki) / config['sidebar'])
        else:
            sidebar_body = ''
        for root, dirs, files in os.walk(dir_wiki):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            files = [f for f in files if not f.startswith('.')]
            readable_path = root[len(dir_wiki)+1:]
            path = scrub_path(readable_path)
            if not os.path.exists(Path(dir_output) / path):
                os.mkdir(Path(dir_output) / path)
            logging.debug(f"processing {files}")
            for file in files:
                logging.debug("main: processing: file:  ",file)
                if 'sidebar' in config and file == config['sidebar']:
                    continue
                clean_name = scrub_path(file)
                if file.lower().endswith('.md'):
                    # parse Markdown file
                    markdown_text, front_matter = read_markdown_and_front_matter(Path(root) / file)
                    if front_matter is False:
                        print(f"NOTE: YAML syntax error in front matter of '{Path(root) / file}'")
                        front_matter = {}
                    # output JSON of front matter
                    (Path(dir_output) / path / clean_name).with_suffix(".json").write_text(json.dumps(front_matter, indent=2, default=datetime_date_serializer))

                    # render and output HTML
                    markdown.reset() # needed for footnotes extension
                    markdown_body = markdown.convert(markdown_text)
                    html = page.render(
                        build_time=build_time,
                        wiki_title=config['wiki_title'],
                        author=config['author'],
                        repo=config['repo'],
                        license=config['license'],
                        title=file[:-3],
                        markdown_body=markdown_body,
                        sidebar_body=sidebar_body
                    )
                    (Path(dir_output) / path / clean_name).with_suffix(".html").write_text(html)

                    # remember this page for All Pages
                    all_pages.append({'title':f"{readable_path}/{file[:-3]}", 'path':f"{path}/{clean_name[:-3]}.html"})
                # copy all original files
                logging.debug("copy all original files")
                shutil.copy(Path(root) / file, Path(dir_output) / path / clean_name)

        # copy README.html to index.html if no index.html
        logging.debug("copy README.html to index.html if no index.html")
        if not os.path.exists(Path(dir_output) / 'index.html'):
            shutil.copyfile(Path(dir_output) / 'README.html', Path(dir_output) / 'index.html')

        # copy static assets directory
        logging.debug("copy static assets directory")
        if os.path.exists(Path(dir_templates) / 'mwb-static'):
            shutil.copytree(Path(dir_templates) / 'mwb-static', Path(dir_output) / 'mwb-static')

        # build all-pages.html
        logging.debug("build all-pages.html")
        all_pages = sorted(all_pages, key=lambda i: i['title'].lower())
        html = j.get_template('all-pages.html').render(
            build_time=build_time,
            pages=all_pages,
            wiki_title=config['wiki_title'],
            author=config['author'],
            repo=config['repo'],
            license=config['license']
        )
        (Path(dir_output) / "all-pages.html").write_text(html)

        # done
        logging.debug("done")

    except Exception as e:
        traceback.print_exc(e)

if __name__ == "__main__":
    exit(main())
