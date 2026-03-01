#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2016 Code Knights
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Plagiarism checker for submissions.

This module compares submissions to detect potential plagiarism
using sequence matching algorithms.
"""

import json
import logging
import re
from difflib import SequenceMatcher

from cms.db.submission import Submission, File
from cms.db.user import Participation

logger = logging.getLogger(__name__)

# Regular expressions for cleaning source code
comment_re = re.compile(r'(//.*|/\*[\s\S]*?\*/)', re.MULTILINE)
preprocessor_re = re.compile(r'#.*', re.MULTILINE)
whitespace_re = re.compile(r'\s', re.MULTILINE)

# Configuration defaults (can be overridden via config)
PLAGIARISM_IGNORE_PREPROCESSOR = True
PLAGIARISM_IGNORE_COMMENTS = True
PLAGIARISM_IGNORE_WHITESPACE = True


def clean_text(text, ignore_preprocessor=True, ignore_comments=True,
               ignore_whitespace=True):
    """Clean source code text for comparison.

    Args:
        text: The source code text to clean.
        ignore_preprocessor: If True, remove preprocessor directives.
        ignore_comments: If True, remove C/C++ style comments.
        ignore_whitespace: If True, remove all whitespace.

    Returns:
        The cleaned text.
    """
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')

    if ignore_preprocessor:
        text = preprocessor_re.sub('', text)
    if ignore_comments:
        text = comment_re.sub('', text)
    if ignore_whitespace:
        text = whitespace_re.sub('', text)
    return text


def calculate_plagiarism(submission, session, file_cacher,
                        ignore_preprocessor=PLAGIARISM_IGNORE_PREPROCESSOR,
                        ignore_comments=PLAGIARISM_IGNORE_COMMENTS,
                        ignore_whitespace=PLAGIARISM_IGNORE_WHITESPACE):
    """Check a submission for plagiarism against earlier submissions.

    Compares the submission against all earlier submissions for the same
    task from other participants using sequence matching.

    Args:
        submission: The Submission object to check.
        session: SQLAlchemy session.
        file_cacher: File cacher for retrieving submission files.
        ignore_preprocessor: If True, ignore preprocessor directives.
        ignore_comments: If True, ignore comments.
        ignore_whitespace: If True, ignore whitespace.

    Returns:
        A tuple of (result_string, details_json) where result_string is
        a human-readable summary and details_json contains detailed
        comparison data for all compared submissions.
    """
    logger.info("Plagiarism check on submission id %s", submission.id)

    submission.plagiarism_check_result = None
    submission.plagiarism_check_details = None

    # Get the file content for this submission
    file_obj = session.query(File).filter(
        File.submission == submission).first()
    if file_obj is None:
        submission.plagiarism_check_result = "No file found"
        return

    base_string = file_cacher.get_file_content(file_obj.digest)
    base_string = clean_text(base_string, ignore_preprocessor,
                            ignore_comments, ignore_whitespace)

    # Find submissions of the same task from other participations
    # that were submitted before this one
    query = session.query(Submission).join(Participation) \
        .order_by(Submission.id) \
        .filter(Participation.contest_id ==
                submission.participation.contest_id) \
        .filter(Submission.participation_id != submission.participation_id) \
        .filter(Submission.timestamp < submission.timestamp) \
        .filter(Submission.task_id == submission.task_id)

    highest_ratio = 0
    submission.plagiarism_check_result = "No submission to compare"
    details = []

    # The matcher caches information about the second sequence
    # With this, it should be faster
    matcher = SequenceMatcher(None, "", base_string)

    for sub in query:
        file_b = session.query(File).filter(File.submission == sub).first()
        if file_b is None:
            continue

        compare_string = file_cacher.get_file_content(file_b.digest)
        compare_string = clean_text(compare_string, ignore_preprocessor,
                                   ignore_comments, ignore_whitespace)

        matcher.set_seq1(compare_string)
        ratio = matcher.ratio()

        username = sub.participation.user.username
        if ratio > highest_ratio:
            highest_ratio = ratio
            submission.plagiarism_check_result = \
                "%.2f against %s" % (ratio, username)

        details.append({
            "submission_timestamp": str(sub.timestamp),
            "submission_id": sub.id,
            "username": username,
            "user_id": sub.participation.user_id,
            "ratio": ratio
        })

    submission.plagiarism_check_details = json.dumps(
        details, sort_keys=True, indent=4, separators=(',', ': '))
