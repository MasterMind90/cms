#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
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

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json
import datetime
from cms.db import SessionGen, Submission, SubmissionResult
from cms.grading.ScoreType import ScoreType

# Dummy function to mark translatable string.
def N_(message):
    return message

# A scoring that tries to approximate ACM-ICPC style ranking system.
# The parameter is an array of two number [base,penalty]
# If all testcase is correct, the score would be base - (previous wrong submission) * penalty
# Not the most perfect solution, but it work.
class ACMICPCApproximate(ScoreType):
    """The score of a submission is the sum of the outcomes,
    multiplied by the integer parameter.

    """
    # Mark strings for localization.
    N_("Outcome")
    N_("Details")
    N_("Execution time")
    N_("Memory used")
    N_("N/A")
    TEMPLATE = """\
{% from cms.grading import format_status_text %}
{% from cms.server import format_size %}

Base : {{ details["base"] }}<br />
Wrong Attempt : {{ details["wrong_attempt"] }}<br />
Penalty : {{ details["penalty"] }}<br />
Second Elapsed : {{ details["second_elapsed"] }}<br />
Time Penalty : {{ details["time_penalty"] }}<br />
<table class="testcase-list">
    <thead>
        <tr>
            <th>{{ _("Outcome") }}</th>
            <th>{{ _("Details") }}</th>
            <th>{{ _("Execution time") }}</th>
            <th>{{ _("Memory used") }}</th>
        </tr>
    </thead>
    <tbody>
    {% for tc in details["testcases"] %}
        {% if "outcome" in tc and "text" in tc %}
            {% if tc["outcome"] == "Correct" %}
        <tr class="correct">
            {% elif tc["outcome"] == "Not correct" %}
        <tr class="notcorrect">
            {% else %}
        <tr class="partiallycorrect">
            {% end %}
            <td>{{ _(tc["outcome"]) }}</td>
            <td>{{ format_status_text(tc["text"], _) }}</td>
            <td>
            {% if tc["time"] is not None %}
                {{ _("%(seconds)0.3f s") % {'seconds': tc["time"]} }}
            {% else %}
                {{ _("N/A") }}
            {% end %}
            </td>
            <td>
            {% if tc["memory"] is not None %}
                {{ format_size(tc["memory"]) }}
            {% else %}
                {{ _("N/A") }}
            {% end %}
            </td>
        {% else %}
        <tr class="undefined">
            <td colspan="4">
                {{ _("N/A") }}
            </td>
        </tr>
        {% end %}
    {% end %}
    </tbody>
</table>"""

    def params(self):
        base = 10000
        penalty = 20
        time_decay = 1
        if isinstance(self.parameters, list):
            if len(self.parameters) > 0:
                base = self.parameters[0]
            if len(self.parameters) > 1:
                penalty = self.parameters[1]
            if len(self.parameters) > 2:
                time_decay = self.parameters[2]
        else:
            base = self.parameters

        return base, penalty, time_decay

    def max_scores(self):
        """See ScoreType.max_score."""
        base, penalty, time_decay = self.params()
        public_score = base
        score = base
        return score, public_score, []

    def compute_score(self, submission_result):
        """See ScoreType.compute_score."""
        # Actually, this means it didn't even compile!
        if not submission_result.evaluated():
            return None, "[]", None, "[]", json.dumps([])

        with SessionGen() as session:
            base, penalty, time_decay = self.params()

            # XXX Lexicographical order by codename
            indices = sorted(self.public_testcases.keys())
            evaluations = dict((ev.codename, ev)
                               for ev in submission_result.evaluations)
            testcases = []
            public_testcases = []
            has_wrong = False

            for idx in indices:
                this_score = float(evaluations[idx].outcome)
                tc_outcome = self.get_public_outcome(this_score)
                if this_score <= 0.0:
                    has_wrong = True
                testcases.append({
                    "idx": idx,
                    "outcome": tc_outcome,
                    "text": evaluations[idx].text,
                    "time": evaluations[idx].execution_time,
                    "memory": evaluations[idx].execution_memory,
                    })
                if self.public_testcases[idx]:
                    public_testcases.append(testcases[-1])
                else:
                    public_testcases.append({"idx": idx})

            score = base
            before_count = session.query(Submission).join(SubmissionResult) \
                .filter(Submission.timestamp < submission_result.submission.timestamp) \
                .filter(Submission.task_id == submission_result.submission.task_id) \
                .filter(SubmissionResult.score == 0) \
                .count()
            score -= before_count*penalty

            contest_start = submission_result.submission.task.contest.start
            second_elapsed = (submission_result.submission.timestamp - contest_start).total_seconds()
            time_penalty = time_decay * second_elapsed
            score -= time_penalty

            details = {
                "base": base,
                "wrong_attempt": before_count,
                "penalty": penalty*before_count,
                "second_elapsed": second_elapsed,
                "time_penalty": time_penalty
            }

            if has_wrong:
                details = {
                    "base": 0,
                    "wrong_attempt": before_count,
                    "penalty": 0,
                    "second_elapsed": second_elapsed,
                    "time_penalty": time_penalty
                }
                score = 0

            public_score = score
            public_details = details.copy()
            to_rws = details.copy()

            details['testcases'] = testcases
            public_details['testcases'] = public_testcases

            return score, json.dumps(details), \
                public_score, json.dumps(public_details), \
                json.dumps([json.dumps(to_rws)])

    def get_public_outcome(self, outcome):
        """Return a public outcome from an outcome.

        outcome (float): the outcome of the submission.

        return (float): the public output.

        """

        if outcome <= 0.0:
            return N_("Not correct")
        elif outcome >= self.parameters:
            return N_("Correct")
        else:
            return N_("Partially correct")
