#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/

"""Balloon-related handlers for AWS."""

from cms.db import Balloon, Contest, Task
from cmscommon.datetime import make_datetime
from .base import BaseHandler, require_permission


class ContestBalloonsHandler(BaseHandler):
    """Shows the balloon dashboard for a contest."""

    @require_permission(BaseHandler.AUTHENTICATED)
    def get(self, contest_id):
        contest = self.safe_get_item(Contest, contest_id)
        self.contest = contest

        balloons = self.sql_session.query(Balloon)\
            .join(Task, Balloon.task_id == Task.id)\
            .filter(Task.contest_id == contest.id)\
            .order_by(Balloon.delivered.asc(),
                      Balloon.id.desc())\
            .all()

        self.r_params = self.render_params()
        self.r_params["balloons"] = balloons
        self.render("balloons.html", **self.r_params)


class BalloonDeliverHandler(BaseHandler):
    """Marks a balloon as delivered (or undelivered)."""

    @require_permission(BaseHandler.AUTHENTICATED)
    def post(self, balloon_id):
        balloon = self.safe_get_item(Balloon, balloon_id)
        contest_id = balloon.task.contest_id

        balloon.delivered = not balloon.delivered
        balloon.delivered_at = make_datetime() if balloon.delivered else None

        self.try_commit()
        self.redirect(self.url("contest", contest_id, "balloons"))
