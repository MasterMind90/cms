#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2015 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
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

"""The service that forwards data to RankingWebServer.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json
import logging
import string

import gevent
import gevent.queue

import requests
import requests.exceptions
from urlparse import urljoin, urlsplit
from sqlalchemy import func

from cms import config
from cms.io import Executor, QueueItem, TriggeredService, rpc_method
from cms.db import SessionGen, Contest, Task, Submission, SubmissionResult
from cms.grading.scoretypes import get_score_type
from cmscommon.datetime import make_timestamp


logger = logging.getLogger(__name__)


class CannotSendError(Exception):
    pass


def encode_id(entity_id):
    """Encode the id using only A-Za-z0-9_.

    entity_id (unicode): the entity id to encode.
    return (unicode): encoded entity id.

    """
    encoded_id = ""
    for char in entity_id.encode('utf-8'):
        if char not in string.ascii_letters + string.digits:
            encoded_id += "_%x" % ord(char)
        else:
            encoded_id += unicode(char)
    return encoded_id


def safe_put_data(ranking, resource, data, operation):
    """Send some data to ranking using a PUT request.

    ranking (bytes): the URL of ranking server.
    resource (bytes): the relative path of the entity.
    data (dict): the data to JSON-encode and send.
    operation (unicode): a human-readable description of the operation
        we're performing (to produce log messages).

    raise (CannotSendError): in case of communication errors.

    """
    try:
        url = urljoin(ranking, resource)
        # XXX With requests-1.2 auth is automatically extracted from
        # the URL: there is no need for this.
        auth = urlsplit(url)
        res = requests.put(url, json.dumps(data, encoding="utf-8"),
                           auth=(auth.username, auth.password),
                           headers={'content-type': 'application/json'},
                           verify=config.https_certfile)
    except requests.exceptions.RequestException as error:
        msg = "%s while %s: %s." % (type(error).__name__, operation, error)
        logger.warning(msg)
        raise CannotSendError(msg)
    if 400 <= res.status_code < 600:
        msg = "Status %s while %s." % (res.status_code, operation)
        logger.warning(msg)
        raise CannotSendError(msg)


class ProxyOperation(QueueItem):
    def __init__(self, type_, data):
        self.type_ = type_
        self.data = data

    def __str__(self):
        return "sending data of type %s to ranking" % (
            self.type_)

    def to_dict(self):
        return {"type": self.type_,
                "data": self.data}


class ProxyExecutor(Executor):
    """A thread that sends data to one ranking.

    The object is used as a thread-local storage and its run method is
    the function that, started as a greenlet, uses it.

    It maintains a queue of data to send. At each "round" the queue is
    emptied (i.e. all jobs are fetched) and the data is then "combined"
    to minimize the number of actual HTTP requests: they'll be at most
    one per entity type.

    Each entity type is identified by a integral class-level constant.

    """

    # We use a single queue for all the data we have to send to the
    # ranking so we need to distingush the type of each item.
    CONTEST_TYPE = 0
    TASK_TYPE = 1
    TEAM_TYPE = 2
    USER_TYPE = 3
    SUBMISSION_TYPE = 4
    SUBCHANGE_TYPE = 5

    # The resource paths for the different entity types, relative to
    # the self.ranking URL.
    RESOURCE_PATHS = [
        b"contests",
        b"tasks",
        b"teams",
        b"users",
        b"submissions",
        b"subchanges"]

    # How many different entity types we know about.
    TYPE_COUNT = len(RESOURCE_PATHS)

    # How long we wait after having failed to push data to a ranking
    # before trying again.
    FAILURE_WAIT = 5.0

    def __init__(self, ranking):
        """Create a proxy for the ranking at the given URL.

        ranking (bytes): a complete URL (containing protocol, username,
            password, hostname, port and prefix) where a ranking is
            supposed to listen.

        """
        super(ProxyExecutor, self).__init__(batch_executions=True)

        self._ranking = ranking

    def execute(self, entries):
        """Consume (i.e. send) the data put in the queue, forever.

        Pick all operations found in the queue (if there aren't any,
        block waiting until there are), combine them and send HTTP
        requests to the target ranking. Do it until something very bad
        happens (i.e. some exception is raised). If communication fails
        don't stop, just wait FAILURE_WAIT seconds before restarting
        the loop.

        Do all this cooperatively: yield at every blocking operation
        (queue fetch, request send, failure wait, etc.). Since the
        queue is joinable, also notify when the fetched jobs are done.

        entries ([QueueEntry]): entries containing the operations to
            perform.

        """
        # The cumulative data that we will try to send to the ranking,
        # built by combining items in the queue.
        data = list(dict() for i in xrange(self.TYPE_COUNT))

        for entry in entries:
            data[entry.item.type_].update(entry.item.data)

        try:
            for i in xrange(self.TYPE_COUNT):
                # Send entities of type i.
                if len(data[i]) > 0:
                    # We abuse the resource path as the English
                    # (plural) name for the entity type.
                    name = self.RESOURCE_PATHS[i]
                    operation = "sending %s to ranking %s" % (name,
                                                              self._ranking)

                    logger.debug(operation.capitalize())
                    safe_put_data(
                        self._ranking, b"%s/" % name, data[i], operation)
                    data[i].clear()

        except CannotSendError:
            # A log message has already been produced.
            gevent.sleep(self.FAILURE_WAIT)
        except:
            # Whoa! That's unexpected!
            logger.error("Unexpected error.", exc_info=True)
            gevent.sleep(self.FAILURE_WAIT)


class ProxyService(TriggeredService):
    """Maintain the information held by rankings up-to-date.

    Discover (by receiving notifications and by periodically sweeping
    over the database) when relevant data changes happen and forward
    them to the rankings by putting them in the queues of the proxies.

    The "entry points" are submission_score, submission_tokened,
    dataset_updated (and search_operations_not_done, from triggered
    service, which is also periodically executed). These methods fetch
    objects from the database, check their validity (existence,
    non-hiddenness, etc.)  and status and, if needed, put call
    initialize, send_score and send_token that construct the data to
    send to rankings and put it in the queues of all proxies.

    """

    def __init__(self, shard, contest_id):
        """Start the service with the given parameters.

        Create an instance of the ProxyService and make it listen on
        the address corresponding to the given shard. Tell it to
        manage data for the contest with the given ID.

        shard (int): the shard of the service, i.e. this instance
            corresponds to the shard-th entry in the list of addresses
            (hostname/port pairs) for this kind of service in the
            configuration file.
        contest_id (int): the ID of the contest to manage.

        """
        super(ProxyService, self).__init__(shard)

        self.contest_id = contest_id

        # Store what data we already sent to rankings, to avoid
        # sending it twice.
        self.scores_sent_to_rankings = set()
        self.tokens_sent_to_rankings = set()

        # Create one executor for each ranking.
        self.rankings = list()
        for ranking in config.rankings:
            self.add_executor(ProxyExecutor(ranking.encode('utf-8')))
        self.start_sweeper(347.0)

        # Send some initial data to rankings.
        self.initialize()

    def _missing_operations(self):
        """Return a generator of data to be sent to the rankings..

        """
        counter = 0
        with SessionGen() as session:
            contest = Contest.get_from_id(self.contest_id, session)

            for submission in contest.get_submissions():
                if submission.user.hidden:
                    continue

                # The submission result can be None if the dataset has
                # been just made live.
                sr = submission.get_result()
                if sr is None:
                    continue

                if sr.scored() and \
                        submission.id not in self.scores_sent_to_rankings:
                    for operation in self.operations_for_score(submission):
                        self.enqueue(operation)
                        counter += 1

                if submission.tokened() and \
                        submission.id not in self.tokens_sent_to_rankings:
                    for operation in self.operations_for_token(submission):
                        self.enqueue(operation)
                        counter += 1

        return counter

    def initialize(self):
        """Send basic data to all the rankings.

        It's data that's supposed to be sent before the contest, that's
        needed to understand what we're talking about when we send
        submissions: contest, users, tasks.

        No support for teams, flags and faces.

        """
        logger.info("Initializing rankings.")

        with SessionGen() as session:
            contest = Contest.get_from_id(self.contest_id, session)

            if contest is None:
                logger.error("Received request for unexistent contest "
                             "id %s.", self.contest_id)
                raise KeyError("Contest not found.")

            contest_id = encode_id(contest.name)
            contest_data = {
                "name": contest.description,
                "begin": int(make_timestamp(contest.start)),
                "end": int(make_timestamp(contest.stop)),
                "freeze_time": int(make_timestamp(contest.freeze_time)),
                "score_precision": contest.score_precision}

            users = dict()

            for user in contest.users:
                if not user.hidden:
                    users[encode_id(user.username)] = \
                        {"f_name": user.first_name,
                         "l_name": user.last_name,
                         "team": None}

            tasks = dict()

            for task in contest.tasks:
                score_type = get_score_type(dataset=task.active_dataset)
                tasks[encode_id(task.name)] = \
                    {"short_name": task.name,
                     "name": task.title,
                     "contest": encode_id(contest.name),
                     "order": task.num,
                     "max_score": score_type.max_score,
                     "extra_headers": score_type.ranking_headers,
                     "score_precision": task.score_precision,
                     "score_mode": task.score_mode,
                     "score_type": score_type.__class__.__name__ }

        self.enqueue(ProxyOperation(ProxyExecutor.CONTEST_TYPE,
                                    {contest_id: contest_data}))
        self.enqueue(ProxyOperation(ProxyExecutor.USER_TYPE, users))
        self.enqueue(ProxyOperation(ProxyExecutor.TASK_TYPE, tasks))

    def operations_for_score(self, submission):
        """Send the score for the given submission to all rankings.

        Put the submission and its score subchange in all the proxy
        queues for them to be sent to rankings.

        """
        submission_result = submission.get_result()

        # Data to send to remote rankings.
        submission_id = "%d" % submission.id
        submission_data = {
            "user": encode_id(submission.user.username),
            "task": encode_id(submission.task.name),
            "time": int(make_timestamp(submission.timestamp))}

        subchange_id = "%d%ss" % (make_timestamp(submission.timestamp),
                                  submission_id)
        subchange_data = {
            "submission": submission_id,
            "time": int(make_timestamp(submission.timestamp))}

        # This check is probably useless.
        if submission_result is not None and submission_result.scored():

            with SessionGen() as session:
                # Not sending data to the ranking if the submission is after the freeze time.
                # But the ranking board need to know something was sent.
                # So we will modify the score so that it would be insignificantly higher
                # than what was previously achieved if it was achieved

                contest = submission.task.contest
                score_to_send = submission_result.score

                if submission.timestamp > contest.freeze_time and score_to_send != 0.0:

                    previous_score = session.query(func.max(SubmissionResult.score)) \
                        .join(Submission) \
                        .filter(Submission.timestamp < submission.timestamp) \
                        .filter(Submission.task == submission.task) \
                        .filter(Submission.user == submission.user).scalar()

                    if previous_score == None:
                        previous_score = 0.0

                    if submission.task.active_dataset.score_type == "ACMICPCApproximate":
                        # For ACMICPC rule, if previous score is already nonzero (correct),
                        # Then just send 0.0. It should be ignored in the ranking server.
                        if previous_score == 0.0:
                            score_to_send = previous_score+0.01
                        else:
                            score_to_send = 0.0
                    else:
                        score_to_send = previous_score+0.01

                # We're sending the unrounded score to RWS
                subchange_data["score"] = score_to_send
                subchange_data["extra"] = \
                    json.loads(submission_result.ranking_score_details)

        self.scores_sent_to_rankings.add(submission.id)

        return [
            ProxyOperation(ProxyExecutor.SUBMISSION_TYPE,
                           {submission_id: submission_data}),
            ProxyOperation(ProxyExecutor.SUBCHANGE_TYPE,
                           {subchange_id: subchange_data})]

    def operations_for_token(self, submission):
        """Send the token for the given submission to all rankings.

        Put the submission and its token subchange in all the proxy
        queues for them to be sent to rankings.

        """
        # Data to send to remote rankings.
        submission_id = "%d" % submission.id
        submission_data = {
            "user": encode_id(submission.user.username),
            "task": encode_id(submission.task.name),
            "time": int(make_timestamp(submission.timestamp))}

        subchange_id = "%d%st" % (make_timestamp(submission.token.timestamp),
                                  submission_id)
        subchange_data = {
            "submission": submission_id,
            "time": int(make_timestamp(submission.token.timestamp)),
            "token": True}

        self.tokens_sent_to_rankings.add(submission.id)

        return [
            ProxyOperation(ProxyExecutor.SUBMISSION_TYPE,
                           {submission_id: submission_data}),
            ProxyOperation(ProxyExecutor.SUBCHANGE_TYPE,
                           {subchange_id: subchange_data})]

    @rpc_method
    def reinitialize(self):
        """Repeat the initialization procedure for all rankings.

        This method is usually called via RPC when someone knows that
        some basic data (i.e. contest, tasks or users) changed and
        rankings need to be updated.

        """
        logger.info("Reinitializing rankings.")
        self.initialize()

    @rpc_method
    def submission_scored(self, submission_id):
        """Notice that a submission has been scored.

        Usually called by ScoringService when it's done with scoring a
        submission result. Since we don't trust anyone we verify that,
        and then send data about the score to the rankings.

        submission_id (int): the id of the submission that changed.
        dataset_id (int): the id of the dataset to use.

        """
        with SessionGen() as session:
            submission = Submission.get_from_id(submission_id, session)

            if submission is None:
                logger.error("[submission_scored] Received score request for "
                             "unexistent submission id %s.", submission_id)
                raise KeyError("Submission not found.")

            if submission.user.hidden:
                logger.info("[submission_scored] Score for submission %d "
                            "not sent because user is hidden.", submission_id)
                return

            # Update RWS.
            for operation in self.operations_for_score(submission):
                self.enqueue(operation)

    @rpc_method
    def submission_tokened(self, submission_id):
        """Notice that a submission has been tokened.

        Usually called by ContestWebServer when it's processing a token
        request of an user. Since we don't trust anyone we verify that,
        and then send data about the token to the rankings.

        submission_id (int): the id of the submission that changed.

        """
        with SessionGen() as session:
            submission = Submission.get_from_id(submission_id, session)

            if submission is None:
                logger.error("[submission_tokened] Received token request for "
                             "unexistent submission id %s.", submission_id)
                raise KeyError("Submission not found.")

            if submission.user.hidden:
                logger.info("[submission_tokened] Token for submission %d "
                            "not sent because user is hidden.", submission_id)
                return

            # Update RWS.
            for operation in self.operations_for_token(submission):
                self.enqueue(operation)

    @rpc_method
    def update_all(self, args=None):
        """ A utility rpc that update the ranking server of all data
        """
        self.reinitialize();
        with SessionGen() as session:
            contest = Contest.get_from_id(self.contest_id, session)
            for submission in session.query(Submission).join(Task) \
                .filter(Task.contest == contest).all():
                # Update RWS.
                if not submission.user.hidden and \
                        submission.get_result() is not None and \
                        submission.get_result().scored():
                    for operation in self.operations_for_score(submission):
                        self.enqueue(operation)

    @rpc_method
    def dataset_updated(self, task_id):
        """Notice that the active dataset of a task has been changed.

        Usually called by AdminWebServer when the contest administrator
        changed the active dataset of a task. This means that we should
        update all the scores for the task using the submission results
        on the new active dataset. If some of them are not available
        yet we keep the old scores (we don't delete them!) and wait for
        ScoringService to notify us that the new ones are available.

        task_id (int): the ID of the task whose dataset has changed.

        """
        with SessionGen() as session:
            task = Task.get_from_id(task_id, session)
            dataset = task.active_dataset

            logger.info("Dataset update for task %d (dataset now is %d).",
                        task.id, dataset.id)

            # max_score and/or extra_headers might have changed.
            self.reinitialize()

            for submission in task.submissions:
                # Update RWS.
                if not submission.user.hidden and \
                        submission.get_result() is not None and \
                        submission.get_result().scored():
                    for operation in self.operations_for_score(submission):
                        self.enqueue(operation)
