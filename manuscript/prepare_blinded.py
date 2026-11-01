"""Make the review copy from the current authored Quarto manuscript."""

from pathlib import Path
import argparse
import os
import re
import subprocess

import pikepdf


HERE = Path(__file__).resolve().parent


def strip_pdf_metadata(source, destination):
    with pikepdf.Pdf.open(source) as pdf:
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
        if '/Metadata' in pdf.Root:
            del pdf.Root['/Metadata']
        pdf.save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    source = (HERE / 'beyond_stimulus_sampling.qmd').read_text()
    front, body = source.split('---\n', 2)[1:]
    front = re.sub(r'(?ms)^author:\n.*?(?=^abstract:)',
                   'author:\n  - name: "Anonymous"\n    corresponding: true\n'
                   '    affiliations:\n      - name: "Anonymous institution"\n', front)
    front = re.sub(r'(?ms)^author-note:\n.*?(?=^date:)', '', front)
    front = front.replace('    mask: false', '    mask: true')
    front += ('suppress-author: true\nsuppress-affiliation: true\n'
              'suppress-author-note: true\nsuppress-orcid: true\n')
    body = body.replace('stimulus_family_audit.pdf', 'stimulus_family_audit_blinded.pdf')
    target = HERE / 'beyond_stimulus_sampling_blinded.qmd'
    target.write_text('---\n' + front + '---\n' + body)
    strip_pdf_metadata(HERE / 'stimulus_family_audit.pdf',
                       HERE / 'stimulus_family_audit_blinded.pdf')
    if args.render:
        environment = os.environ.copy()
        environment.setdefault('XDG_CACHE_HOME', '/tmp/bss-quarto-cache')
        subprocess.run(['quarto', 'render', target.name, '--to', 'apaquarto-pdf', '--quiet'],
                       cwd=HERE, env=environment, check=True)
        temporary = target.with_suffix('.metadata-clean.pdf')
        strip_pdf_metadata(target.with_suffix('.pdf'), temporary)
        temporary.replace(target.with_suffix('.pdf'))
        text = subprocess.run(['pdftotext', str(target.with_suffix('.pdf')), '-'],
                              check=True, capture_output=True, text=True).stdout
        for identifying in ('David Hagmann', 'Zachary Wojtowicz', 'hagmann@ust.hk',
                            'Hong Kong University of Science', 'Massachusetts Institute',
                            '0000-0002-2080-997X'):
            assert identifying not in text, identifying
        assert 'https://github.com/dhagmann/beyond-stimulus-sampling' in re.sub(r'\s+', '', text)
        assert '??' not in text
        print('Blinded review PDF prepared; requested GitHub URL remains in the footnote.')
    else:
        print('Blinded Quarto source and audit prepared.')


if __name__ == '__main__':
    main()
