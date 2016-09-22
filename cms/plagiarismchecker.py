from difflib import SequenceMatcher
from cms.db.submission import Submission, File
from cms.db.user import Participation
import json
import logging

logger = logging.getLogger(__name__)

def calculate_plagiarism(submission, session, file_cacher):
    logger.info("Plagiarism check on submission id %s"%submission.id)
    
    submission.plagiarism_check_result = None
    submission.plagiarism_check_details = None

    digest_a = session.query(File).filter(File.submission == submission).first().digest
    base_string = file_cacher.get_file_content(digest_a)

    # Find submissions of the same task from other
    # participation
    query = session.query(Submission).join(Participation) \
                .order_by(Submission.id) \
                .filter(Participation.contest_id == submission.participation.contest_id) \
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
        digest_b = session.query(File).filter(File.submission == sub).first().digest
        compare_string = file_cacher.get_file_content(digest_b)

        matcher.set_seq1(compare_string)
        ratio = matcher.ratio()

        username = sub.participation.user.username
        if ratio > highest_ratio:
            highest_ratio = ratio
            submission.plagiarism_check_result = "%.2f against %s"%(ratio, username)
        details.append({
            "submission_timestamp" : str(sub.timestamp),
            "submission_id" : sub.id,
            "username" : username,
            "user_id" : sub.participation.user_id,
            "ratio" : ratio
        })

    submission.plagiarism_check_details = json.dumps(details, sort_keys=True,
        indent=4, separators=(',', ': '))
