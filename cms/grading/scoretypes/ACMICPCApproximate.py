#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2016 Muhammad Amirul Ashraf <asdacap@gmail.com>
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

import logging

from cms.db import SessionGen, Submission, SubmissionResult
from cms.grading import format_status_text
from cms.locale import DEFAULT_TRANSLATION
from . import ScoreTypeAlone


logger = logging.getLogger(__name__)


# Dummy function to mark translatable string.
def N_(message):
    return message


class ACMICPCApproximate(ScoreTypeAlone):
    """A scoring that approximates ACM-ICPC style ranking system.

    The parameter is an array of up to three numbers [base, penalty, time_decay]:
    - base: The base score for a correct submission (default: 10000)
    - penalty: Points deducted per wrong submission (default: 20)
    - time_decay: Points deducted per second elapsed (default: 1)

    If all testcases are correct, the score is:
        base - (previous_wrong_submissions * penalty) - (seconds_elapsed * time_decay)

    If any testcase fails, the score is 0.
    """
    # Mark strings for localization.
    N_("Outcome")
    N_("Details")
    N_("Execution time")
    N_("Memory used")
    N_("N/A")
    TEMPLATE = """\
<div class="acmicpc-summary">
    <table class="table table-condensed">
        <tr><td>{% trans %}Base Score{% endtrans %}</td><td>{{ details["base"] }}</td></tr>
        <tr><td>{% trans %}Wrong Attempts{% endtrans %}</td><td>{{ details["wrong_attempt"] }}</td></tr>
        <tr><td>{% trans %}Penalty{% endtrans %}</td><td>{{ details["penalty"] }}</td></tr>
        <tr><td>{% trans %}Seconds Elapsed{% endtrans %}</td><td>{{ details["second_elapsed"]|round(2) }}</td></tr>
        <tr><td>{% trans %}Time Penalty{% endtrans %}</td><td>{{ details["time_penalty"]|round(2) }}</td></tr>
    </table>
</div>
<table class="testcase-list">
    <thead>
        <tr>
            <th class="outcome">{% trans %}Outcome{% endtrans %}</th>
            <th class="details">{% trans %}Details{% endtrans %}</th>
    {% if feedback_level == FEEDBACK_LEVEL_FULL %}
            <th class="execution-time">{% trans %}Execution time{% endtrans %}</th>
            <th class="memory-used">{% trans %}Memory used{% endtrans %}</th>
    {% endif %}
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
            {% endif %}
            <td class="outcome">{{ _(tc["outcome"]) }}</td>
            <td class="details">{{ tc["text"]|format_status_text }}</td>
        {% if feedback_level == FEEDBACK_LEVEL_FULL %}
            <td class="execution-time">
            {% if tc["time"] is not none %}
                {{ tc["time"]|format_duration }}
            {% else %}
                {% trans %}N/A{% endtrans %}
            {% endif %}
            </td>
            <td class="memory-used">
            {% if tc["memory"] is not none %}
                {{ tc["memory"]|format_size }}
            {% else %}
                {% trans %}N/A{% endtrans %}
            {% endif %}
            </td>
        {% endif %}
        </tr>
        {% else %}
        <tr class="undefined">
            <td colspan="4">
                {% trans %}N/A{% endtrans %}
            </td>
        </tr>
        {% endif %}
    {% endfor %}
    </tbody>
</table>"""

    def params(self):
        """Extract parameters from the configuration.

        Returns (tuple): (base, penalty, time_decay)
        """
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

    @staticmethod
    def format_score(score, max_score, unused_score_details,
                     score_precision, translation=DEFAULT_TRANSLATION):
        """Format the score for display in CWS.

        Shows "Accepted" for positive scores, otherwise shows the first
        failing testcase's status text.
        """
        if score > 0:
            return "Accepted"
        else:
            if unused_score_details and "testcases" in unused_score_details:
                for testcase in unused_score_details["testcases"]:
                    if testcase.get("score", 1) <= 0.0:
                        text = testcase.get("text", [])
                        return format_status_text(text, translation)
            return "Not Accepted"

    def compute_score(self, submission_result):
        """See ScoreType.compute_score."""
        with SessionGen() as session:
            base, penalty, time_decay = self.params()

            # XXX Lexicographical order by codename
            indices = sorted(self.public_testcases.keys())
            evaluations = dict((ev.codename, ev)
                               for ev in submission_result.evaluations)
            testcases = []
            public_testcases = []
            has_wrong = False

            if not submission_result.evaluated():
                has_wrong = True
            else:
                for idx in indices:
                    this_score = float(evaluations[idx].outcome)
                    tc_outcome = self.get_public_outcome(this_score)
                    if this_score <= 0.0:
                        has_wrong = True
                    testcases.append({
                        "idx": idx,
                        "score": this_score,
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

            # Count previous wrong submissions for this task by this participant
            before_count = session.query(Submission).join(SubmissionResult) \
                .filter(Submission.timestamp < submission_result.submission.timestamp) \
                .filter(Submission.task_id == submission_result.submission.task_id) \
                .filter(Submission.participation == submission_result.submission.participation) \
                .filter(SubmissionResult.score == 0) \
                .count()

            if has_wrong:  # This submission is also a wrong attempt
                before_count += 1

            score -= before_count * penalty

            # Calculate time penalty
            contest_start = submission_result.submission.task.contest.start
            second_elapsed = (submission_result.submission.timestamp - contest_start).total_seconds()
            time_penalty = time_decay * second_elapsed
            score -= time_penalty

            details = {
                "base": base,
                "wrong_attempt": before_count,
                "penalty": penalty * before_count,
                "second_elapsed": second_elapsed,
                "time_penalty": time_penalty,
                "testcases": testcases,
            }

            if has_wrong:
                details = {
                    "base": 0,
                    "wrong_attempt": before_count,
                    "penalty": 0,
                    "second_elapsed": second_elapsed,
                    "time_penalty": time_penalty,
                    "testcases": testcases,
                }
                score = 0

            public_score = score
            public_details = details.copy()
            public_details["testcases"] = public_testcases

            # For ranking web server
            ranking_details = details.copy()
            del ranking_details["testcases"]

            return score, details, public_score, public_details, [ranking_details]

    def get_public_outcome(self, outcome):
        """Return a public outcome from an outcome.

        outcome (float): the outcome of the submission.

        return (str): the public output.
        """
        if outcome <= 0.0:
            return N_("Not correct")
        elif outcome >= 1.0:
            return N_("Correct")
        else:
            return N_("Partially correct")
