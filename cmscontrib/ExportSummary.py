#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2012 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2010-2011 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2011 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2011 Matteo Boscariol <boscarim@hotmail.com>
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

"""Utility to add a user to a contest.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import sys
import json

from cms import utf8_decoder
from cms.db import SessionGen, User, Contest, \
    Submission, SubmissionResult, ask_for_contest

from cmscommon.datetime import make_timestamp
from collections import OrderedDict


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Export the summary of the contest to a JSON file. "
        "The format is a simple single JSON that can be easily processed."
        "The format is meant to be used for ACM-ICPC style contest for easy"
        "third party script used to show a similar presentation as the "
        "ACM Resolver tool. That means, some of the IOI data will be missing.")
    parser.add_argument("-c", "--contest-id", action="store", type=int,
                        help="id of contest where to add the user")
    parser.add_argument("output", action="store", type=str, nargs="?", default="output.json", help="Output file")

    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    data = OrderedDict()

    with SessionGen() as session:
        contest = Contest.get_from_id(args.contest_id, session)
        data["name"] = contest.name
        data["description"] = contest.description
        data["languages"] = contest.languages
        data["allowed_localizations"] = contest.allowed_localizations
        data["start"] = make_timestamp(contest.start)
        data["stop"] = make_timestamp(contest.stop)
        data["freeze_time"] = make_timestamp(contest.freeze_time)
        data["unfreeze"] = contest.unfreeze

        tasks = OrderedDict()
        for task in contest.tasks:
            outdat = OrderedDict()
            for attr in ["id", "num", "name", "title", "score_mode"]:
                outdat[attr] = getattr(task, attr)
            outdat["score_type"] = task.active_dataset.score_type    
            tasks[task.id] = outdat
        data["tasks"] = tasks

        users = OrderedDict()
        for user in contest.users:
            outdat = OrderedDict()
            for attr in ["id", "first_name", "last_name", \
                "username", "password", "email", "ip", "hidden", "timezone"]:
                outdat[attr] = getattr(user, attr)

            task_submissions = OrderedDict()
            for task in contest.tasks:
                sr = session.query(SubmissionResult).join(Submission) \
                        .filter(Submission.task == task) \
                        .filter(Submission.user == user) \
                        .order_by(SubmissionResult.score, Submission.timestamp.desc())
                if sr.count() == 0:
                    continue
                sr = sr[0]

                tsoutdat = OrderedDict()
                tsoutdat["task_id"] = task.id
                for attr in ["compilation_outcome", "compilation_text", "compilation_tries",
                    "compilation_stdout", "compilation_stderr", "compilation_time",
                    "compilation_wall_clock_time", "compilation_memory", "evaluation_outcome",
                    "evaluation_tries", "score", "score_details", "public_score", "public_score_details", "ranking_score_details"]:
                    tsoutdat[attr] = getattr(sr, attr)
                tsoutdat["timestamp"] = make_timestamp(sr.submission.timestamp)
                tsoutdat["language"] = sr.submission.language
                tsoutdat["comment"] = sr.submission.comment

                task_submissions[task.id] = tsoutdat
            outdat["task_submissions"] = task_submissions


            users[user.id] = outdat
        data["users"] = users

    with open(args.output, 'w') as out:
        json.dump(data, out, sort_keys=False,
                  indent=4, separators=(',', ': '))

    return 0


if __name__ == "__main__":
    sys.exit(main())
