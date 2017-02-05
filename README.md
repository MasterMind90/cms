Contest Management System
=========================

Homepage: <http://cms-dev.github.io/>

[![Build Status](https://travis-ci.org/cms-dev/cms.svg?branch=master)](https://travis-ci.org/cms-dev/cms)
[![Join the chat at https://gitter.im/cms-dev/cms](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/cms-dev/cms?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Introduction
------------

CMS, or Contest Management System, is a distributed system for running
and (to some extent) organizing a programming contest.

CMS has been designed to be general and to handle many different types
of contests, tasks, scorings, etc. Nonetheless, CMS has been
explicitly build to be used in the 2012 International Olympiad in
Informatics, held in September 2012 in Italy.

This Branch
-----------

This branch originally is a fork of CMS v1.2.0. It is modified to be used in
[IIUM Code Jam 2016](http://iiumicpcteam.com/2016/03/iium-code-jam-2016/).
It is modified mainly to provide an ACM-ICPC-like scoring system, but other
changes have been implemented as well. Since them, CMS v1.3.0-prealpha
(of some commit that I don't remember) was merged and more modification was
made to be used in [Code Knights](http://iiumicpcteam.com/2016/06/code-knights/).
Among the differences are:

- A score type called ACMICPCApproximate that tries to approximate
  ACM-ICPC style rankings.
- The scoreboard has minor visual changes when using the
  ACMICPCApproximate score type.
- A contest freeze time in which submission after that time will have a
  different visual cues on the scoreboard.
- A button in admin server that force resending all data to ranking
  server.
- Does not change the filename internally so that java compilation
  works as expected.
- Tags support in the ranking web server and the scoreboard can be filtered
  according to tag. For example 'guest' and 'local' flag.
- It now record stderr and stdout of an evaluation. Available in
  AdminWebServer
- Add an option to allow participants to submit solution outside
  contest time.

ACMICPCApproximate Score Type
-----------------------------

This score type tries to simulate ACM-ICPC ranking system in which there
would be penalty for wrong attempt and faster submission would result in
higher score. It's parameter is an array containing three number `base`,
`penalty` and `time_decay`. The resulting score is `base` - (`penalty`
x `wrong attempt`) - (`time_decay` x `seconds from contest start`).
A good approximation would be [1000,20,0.0166], but it is still possible
for the ranking to behave differently from actual ACM-ICPC ranking system.


Download
--------

**For end-users it's best to download the latest stable version of CMS,
which can be found already packaged at <http://cms-dev.github.io/>.**

This git repository, which contains the development version in its
master branch, is intended for developers and everyone interested in
contributing or just curious to see how the code works and wanting to
hack on it.

Please note that since the sandbox is contained in a [git submodule]
(http://git-scm.com/docs/git-submodule) you should append `--recursive`
to the standard `git clone` command to obtain it. Or, if you have
already cloned CMS, simply run the following command from inside the
repository:

```bash
git submodule update --init
```


Support
-------

The complete CMS documentation is at <https://cms.readthedocs.org/>.

The mailing list for announcements, user support and general discussion
is <contestms@freelists.org>. You can subscribe at
<http://www.freelists.org/list/contestms>. So far, it is an extremely
low traffic mailing list.

The mailing list for development discussion (to submit feedback,
proposals and critics, get opinions and reviews, etc.) is
<contestms-dev@freelists.org>. You can subscribe at
<http://www.freelists.org/list/contestms-dev>.

**Please don't use these mailing lists for bug reports. File them on
[github](https://github.com/cms-dev/cms/issues) instead.**

For extemporaneous support and discussion, join the Gitter chat (see
link above).

To help with the troubleshooting, you can collect the complete log
files that are placed in /var/local/log/cms/ (if CMS was running
installed) or in ./log (if it was running from the local copy).


Testimonials
------------

CMS has been used in several official and unofficial contests. Please
find an updated list at <http://cms-dev.github.io/testimonials.html>.

If you used CMS for a contest, selection, or a similar event, and want
to publicize this information, we would be more than happy to hear
from you and add it to that list.
