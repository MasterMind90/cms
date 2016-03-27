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
import math

from cms import utf8_decoder
from cms.db import SessionGen, User, Contest, Task, Submission, SubmissionResult, ask_for_contest

import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

from datetime import datetime

def add_user(contest_id, first_name, last_name, username,
             password, ip_address, email, hidden):
    with SessionGen() as session:
        contest = Contest.get_from_id(contest_id, session)
        user = User(first_name=first_name,
                    last_name=last_name,
                    username=username,
                    password=password,
                    email=email,
                    ip=ip_address,
                    hidden=hidden,
                    contest=contest)
        session.add(user)
        session.commit()

def time_delta_str(timedelta):
    s = math.floor(timedelta.total_seconds())
    if s < 0:
        s = 0
    hours, remainder = divmod(s, 3600)
    minutes, seconds = divmod(remainder, 60)

    return "%s:%s:%s"%(int(hours), int(minutes), int(seconds))

def date_timestamp(dt):
    return str((dt - datetime(1970, 1, 1)).total_seconds())

def get_problem_status(session, team, time):
    """ Return a list of problem status. Each problem status is a dictionary
    with key "label", "solved", "subs", "time" and "elapsed"

    """

    result = []

    for task in session.query(Task).filter(Task.contest == team.contest):
        pstatus = {}
        pstatus["label"] = task.name

        submissions = session.query(Submission).filter(Submission.task == task) \
            .filter(Submission.user == team) \
            .filter(Submission.timestamp < time)

        pstatus["elapsed"] = 0

        # Later submission after correct is not considered
        first_solve = submissions.join(SubmissionResult).filter(SubmissionResult.score > 0)
        if(first_solve.count() > 0):
            first_solve = first_solve[0]
            submissions = submissions.filter(Submission.timestamp <= first_solve.timestamp)
            pstatus["elapsed"] = (first_solve.timestamp - task.contest.start).total_seconds()

        pstatus["solved"] = submissions.join(SubmissionResult).filter(SubmissionResult.score > 0).count() > 0
        pstatus["subs"] = submissions.count()
        pstatus["time"] = submissions.join(SubmissionResult).filter(SubmissionResult.score == 0).count()*20

        result.append(pstatus)

    return result

def calculate_score_at_time(session, team, time):
    """Also return the number of solved problem and total penalty time

    """
    statuses = get_problem_status(session, team, time)

    total_score = 0
    total_time_penalty = 0
    solved_count = 0
    for stat in statuses:
        if(stat["solved"]):
            solved_count += 1
            total_score += 100000
            total_score -= stat["time"]
            total_score -= stat["elapsed"]*0.016
            total_time_penalty += stat["time"]

    return total_score, total_time_penalty, solved_count

def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Generate an approximation of the CLI CCS Event Feed.")
    parser.add_argument("-c", "--contest-id", action="store", type=int,
                        help="id of contest where to add the user")
    parser.add_argument("-n", "--nationality", action="store", type=str,
                        default="MYS", # I have to put something...
                        help="Team country")
    parser.add_argument("-u", "--university", action="store", type=str,
                        default="IIUM", # I have to put something...
                        help="Team nationality")
    parser.add_argument("output", type=str,
                        nargs="?",
                        default="output.xml",
                        help="Output file")
    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    root_element = ET.Element("contest")
    with SessionGen() as session:
        contest = Contest.get_from_id(args.contest_id, session)
        info = ET.SubElement(root_element, "info")
        ET.SubElement(info, "title").text = contest.name
        ET.SubElement(info, "length").text = time_delta_str(contest.stop-contest.start)
        ET.SubElement(info, "scoreboard-freeze-length").text = \
            time_delta_str(contest.stop-contest.freeze_time)
        ET.SubElement(info, "penalty-amount").text = "20" # Just make it fixed for now.
        ET.SubElement(info, "start-time").text = date_timestamp(contest.start)

        for task in session.query(Task).filter(Task.contest == contest):
            taskel = ET.SubElement(root_element, "task")
            ET.SubElement(taskel, "label").text = task.name
            ET.SubElement(taskel, "name").text = task.title

        # Hardcoded judgement
        judgement = ET.SubElement(root_element, "judgement")
        ET.SubElement(judgement, "acronym").text = "WA"
        ET.SubElement(judgement, "name").text = "Wrong Answer"
        ET.SubElement(judgement, "penalty").text = "true"

        judgement = ET.SubElement(root_element, "judgement")
        ET.SubElement(judgement, "acronym").text = "AC"
        ET.SubElement(judgement, "name").text = "Accepted"
        ET.SubElement(judgement, "penalty").text = "false"

        user_id_number_mapping = {}
        current_user_id_number = 0

        for user in session.query(User).filter(User.contest == contest):
            if user.hidden:
                continue

            user_id_number_mapping[user.id] = current_user_id_number
            current_user_id_number+=1

            userel = ET.SubElement(root_element, "team")
            ET.SubElement(userel, "n").text = str(user_id_number_mapping[user.id])
            ET.SubElement(userel, "name").text = (user.first_name+" "+user.last_name).strip()
            ET.SubElement(userel, "nationality").text = args.nationality
            ET.SubElement(userel, "university").text = args.university

        for submission in session.query(Submission).join(Task).filter(Task.contest == contest):
            if submission.user.hidden:
                continue
            submissionel = ET.SubElement(root_element, "submission")
            ET.SubElement(submissionel, "id").text = str(submission.id)
            ET.SubElement(submissionel, "team-number").text = str(user_id_number_mapping[submission.user_id])
            ET.SubElement(submissionel, "problem-label").text = submission.task.name
            ET.SubElement(submissionel, "language").text = submission.language
            ET.SubElement(submissionel, "timestamp").text = date_timestamp(submission.timestamp)

            sub_result = submission.get_result()
            if(sub_result != None and sub_result.score != None):
                sjudgel = ET.SubElement(submissionel, "submission-judgement")
                ET.SubElement(sjudgel, "submission-id").text = str(submission.id)
                if sub_result.score > 0:
                    ET.SubElement(sjudgel, "judgement").text = "AC"
                else:
                    ET.SubElement(sjudgel, "judgement").text = "WA"

                # CMS don't actually store this time. So assume same as submission time
                ET.SubElement(sjudgel, "contest-time").text = "0"
                ET.SubElement(sjudgel, "timestamp").text = date_timestamp(submission.timestamp)

                scoreboard_update_el = ET.SubElement(sjudgel, "scoreboard-update")

                total_score, total_time_penalty, solved_count = \
                    calculate_score_at_time(session, submission.user, submission.timestamp)

                ET.SubElement(scoreboard_update_el, "sort-key").text = str(total_score)
                ET.SubElement(scoreboard_update_el, "team").text = str(user_id_number_mapping[submission.user_id])
                ET.SubElement(scoreboard_update_el, "solved_count").text = str(solved_count)
                ET.SubElement(scoreboard_update_el, "time").text = str(total_time_penalty)

                for res in get_problem_status(session, submission.user, submission.timestamp):
                    problemel = ET.SubElement(scoreboard_update_el, "problem")
                    ET.SubElement(problemel, "label").text = res["label"]
                    ET.SubElement(problemel, "solved").text = str(res["solved"])
                    ET.SubElement(problemel, "subs").text = str(res["subs"])
                    ET.SubElement(problemel, "time").text = str(res["time"])

        finalized = ET.SubElement(root_element, "finalized")
        ET.SubElement(finalized, "timestamp").text = date_timestamp(contest.stop)
        ET.SubElement(finalized, "last-gold").text = "4"
        ET.SubElement(finalized, "last-silver").text = "8"
        ET.SubElement(finalized, "last-bronze").text = "12"
        ET.SubElement(finalized, "comment").text = "Fake finalization"


    with open(args.output, "w") as f:
        f.write(minidom.parseString(ET.tostring(root_element)).toprettyxml(indent="  "))

    return 0


if __name__ == "__main__":
    sys.exit(main())
