"""Recruiter-question answers come only from the person's standing answers or answers they taught June; the rest is asked."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

# A fictional profile in the same shape as the private one (never the real values).
PROFILE = dict(name='Test Person', email='test@example.invalid', phone='+91 9000000000', currentLocation='Noida, Uttar Pradesh, India',
               preferredLocation='Noida / Delhi NCR; remote OK', nearbyPlaces=['noida', 'delhi', 'new delhi', 'gurugram', 'gurgaon', 'ghaziabad', 'faridabad', 'ncr', 'remote'],
               openAcrossNcr=True, totalExperienceYears=1, relevantExperienceYears=1, noticeDays=0, currentCtcLpa=3.6, expectedCtcLpa=6,
               skills=['html', 'css', 'javascript', 'react', 'python', 'figma', 'ui/ux', 'prompt engineering', 'n8n'], skillsAsk=['node.js', 'next.js', 'git'],
               zeroForOtherSkills=True, ownLaptop=True, laptop='Mac', sixDayWeek=True, startup=True, shifts=True, team=True, pepSelf=False, pepFamily=False,
               usWorkAuth=False, usSponsorship=True, indiaSponsorship=False, previouslyEmployed=False, heardAbout='Naukri', salutation='Mr.',
               voluntary='Prefer not to say', linkedin='https://www.linkedin.com/in/example', qualification='MCA (AI & ML), Example University, 2025',
               lastEmployer='Example Co (last employer, Oct 2022 - Apr 2023)', designation='Junior Analyst', dob='01-01-2000')


class StandingAnswers(unittest.TestCase):
    def ask(self, question, kind='text'):
        from june.job_answers import standing_answer
        return standing_answer(question, kind, PROFILE)

    def test_salary_follows_the_unit_the_question_asks_for(self):
        self.assertEqual(self.ask('What is your current CTC (in Lacs)?'), '3.6')
        self.assertEqual(self.ask('Expected CTC in LPA'), '6')
        self.assertEqual(self.ask('What is your expected salary per month?'), '50000')
        self.assertEqual(self.ask('Current CTC', 'number'), '360000')
        self.assertEqual(self.ask('What is your current salary?'), '3.6 LPA')
        self.assertNotEqual(self.ask('Current CTC', 'number'), '0', 'never zero')

    def test_notice_and_joining(self):
        self.assertEqual(self.ask('What is your notice period?'), 'Immediate joiner')
        self.assertEqual(self.ask('Notice period in days'), '0')
        self.assertEqual(self.ask('Can you join immediately?'), 'Yes')
        self.assertEqual(self.ask('Are you able to start within 15 days?'), 'Yes')

    def test_experience_is_never_inflated_and_unknown_skills_are_zero(self):
        self.assertEqual(self.ask('How many years of experience do you have in React?'), '1')
        self.assertEqual(self.ask('Rate your experience with React'), None, 'no number asked: the person says')
        self.assertEqual(self.ask('Rate your proficiency in Kotlin'), 'Beginner')
        self.assertEqual(self.ask('Years of experience in HTML', 'number'), '1')
        self.assertEqual(self.ask('How many years of experience do you have in Java?'), '0')
        self.assertEqual(self.ask('Total years of experience'), '1')
        self.assertIsNone(self.ask('How many years of experience do you have in Node.js?'), 'on the resume but the months are the person’s to say')
        self.assertEqual(self.ask('Do you have experience with Python?'), 'Yes')
        self.assertEqual(self.ask('Do you have experience with Salesforce?'), 'No')

    def test_office_location_questions_in_any_wording_check_the_actual_place(self):
        for q in ('Are you okay working from our Noida (Noida Extension) office?', 'Are you fine with working from office in Gurugram?',
                  'Are you happy to work from our Delhi office 5 days a week?', 'Are you open to working at our Noida office?',
                  'Would you be comfortable working onsite in Noida?', 'Are you ready to work from office?'):
            self.assertEqual(self.ask(q), 'Yes', q)
        for q in ('Are you okay working from our Bangalore office?', 'Are you willing to relocate to our Pune office?',
                  'Are you okay working from our Noida or Bangalore office?', 'Are you fine with working from office in Okhla?'):
            self.assertIsNone(self.ask(q), q)

    def test_locations_inside_ncr_are_yes_and_anywhere_else_is_asked(self):
        self.assertEqual(self.ask('Are you willing to relocate to Gurugram?'), 'Yes')
        self.assertEqual(self.ask('Are you comfortable working from office in Noida?'), 'Yes')
        self.assertIsNone(self.ask('Are you willing to relocate to Bangalore?'))
        self.assertEqual(self.ask('What is your current location?'), 'Noida, Uttar Pradesh, India')

    def test_profile_facts_and_honest_employment(self):
        self.assertEqual(self.ask('Do you have your own laptop?'), 'Yes')
        self.assertEqual(self.ask('Which laptop do you have?'), 'Mac')
        self.assertEqual(self.ask('Are you okay with rotational night shifts?'), 'Yes')
        self.assertEqual(self.ask('Is any immediate family member a politically exposed person?'), 'No')
        self.assertEqual(self.ask('Are you a politically exposed person?'), 'No')
        self.assertEqual(self.ask('Are you currently employed?'), 'No')
        self.assertEqual(self.ask('Where did you hear about us?'), 'Naukri')

    def test_resume_upload_defers_to_the_profile_resume_and_gap_is_counted_now(self):
        import datetime
        from june.job_answers import choose, standing_answer
        answer = self.ask('Please upload your resume')
        self.assertEqual(choose(answer, ["Upload", "I'll do it later"]), "I'll do it later")
        today = datetime.date.today()
        months = (today.year - 2025) * 12 + today.month - 2
        self.assertEqual(standing_answer('Do you have a career gap? How many months?', 'text', dict(careerGapSince='2025-02', careerGapReason='academic gap')),
                         f'{months} months - academic gap')

    def test_hard_stops_never_get_an_answer(self):
        from june.job_answers import STOP_ANSWER
        for q in ('Enter the OTP sent to your phone', 'Please enter your PAN number', 'Complete the online test to continue', 'Create an account password', 'Bank account number'):
            self.assertIs(self.ask(q), STOP_ANSWER, q)

    def test_anything_not_covered_is_asked_not_guessed(self):
        for q in ('What is your CGPA?', 'Will you sign a 2 year bond?', 'Why should we hire you?', 'Will you attend the walk-in on Saturday?'):
            self.assertIsNone(self.ask(q), q)


class Options(unittest.TestCase):
    def test_answers_pick_the_matching_option_or_none(self):
        from june.job_answers import choose
        self.assertEqual(choose('Yes', ['Yes', 'No']), 'Yes')
        self.assertEqual(choose('No', ['YES', 'NO']), 'NO')
        self.assertEqual(choose('Immediate joiner', ['15 Days or less', '1 Month', '2 Months']), '15 Days or less')
        self.assertEqual(choose('1 year', ['0-1 Years', '1-3 Years']), '0-1 Years')
        self.assertEqual(choose('0', ['Less than 1 year', '1-2 years']), 'Less than 1 year')
        self.assertEqual(choose('Mac', ['Windows', 'Mac', 'Linux']), 'Mac')
        self.assertIsNone(choose('Yes', ['Maybe later', 'Not sure']))
        self.assertIsNone(choose('4', ['10-15 LPA', '15+ LPA']))


class Remembering(unittest.TestCase):
    def test_taught_answers_are_remembered_by_question_and_pending_questions_clear(self):
        from june.job_answers import Profile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jobs.sqlite3'
            def db():
                connection = sqlite3.connect(path); connection.row_factory = sqlite3.Row; return connection
            profile = Profile(Path(tmp) / 'job-profile.json', db)
            self.assertEqual(profile.standing(), {}, 'no private file yet: nothing is assumed')
            profile.ask('What is your CGPA?', ['7-8', '8-9'], '181125000123', 1)
            self.assertEqual(profile.pending()[0]['options'], ['7-8', '8-9'])
            profile.teach('What is your CGPA?', ' 8-9 ', 2)
            self.assertEqual(profile.learned('what is your cgpa'), '8-9')
            self.assertEqual(profile.pending(), [])
            for bad in ('', 'x' * 301, 'a\x00b'):
                with self.assertRaises(ValueError): profile.teach('Q?', bad, 3)



class Similar(unittest.TestCase):
    def profile(self, tmp):
        from june.job_answers import Profile
        path = Path(tmp) / 'jobs.sqlite3'
        def db():
            connection = sqlite3.connect(path); connection.row_factory = sqlite3.Row; return connection
        return Profile(Path(tmp) / 'job-profile.json', db)

    def test_reworded_questions_reuse_answers_but_never_across_places_skills_units_or_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.profile(tmp)
            profile.teach('Do you use AI coding tools in your daily work?', 'Yes, GPT and Claude', 1)
            profile.teach('Are you okay working from our Noida office?', 'Yes', 2)
            profile.teach('How many years of experience do you have with React?', '1', 3)
            profile.teach('What is your expected salary in LPA?', '6', 4)
            sure = lambda q, kind='text', options=(): [(a, s) for _, _, a, s in profile.similar(q, kind, list(options))]
            self.assertEqual(sure('Do you use AI coding tools daily at work?'), [('Yes, GPT and Claude', True)])
            self.assertEqual(sure('Do you use AI coding tools like Cursor, Copilot or ChatGPT in your daily work?'), [('Yes, GPT and Claude', False)],
                             'extra named examples: only with a second opinion')
            self.assertEqual(sure('Are you okay working from our Bangalore office?', 'radio', ['Yes', 'No']), [], 'different place')
            self.assertEqual(sure('How many years of experience do you have with Vue?'), [], 'different skill')
            self.assertEqual(sure('What is your expected salary per month?'), [], 'different unit')
            self.assertEqual(sure('Do you use AI coding tools in your daily work?', 'radio', ['Daily', 'Weekly']), [], 'answer is not one of the choices')
            self.assertEqual(sure('What is your notice period?'), [], 'unrelated')


class Endpoints(unittest.IsolatedAsyncioTestCase):
    async def test_teach_and_forget_are_strict_and_origin_protected(self):
        import httpx
        from types import SimpleNamespace
        from unittest.mock import patch
        from june.app import app
        from june.config import Settings
        from june.jobs import Jobs
        from june.memory_service import Coordinator
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs(Path(tmp))
            jobs.profile.ask('Will you sign a 2 year bond?', ['Yes', 'No'], '181125000123', 1)
            settings = Settings.from_env()
            with patch.multiple(app.state, settings=settings, coordinator=Coordinator(), plans=SimpleNamespace(naukri=jobs), create=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.backend) as client:
                    self.assertEqual((await client.post('/api/jobs/answers', json={'question': 'Q?', 'answer': 'No'}, headers={'Origin': 'https://other.example'})).status_code, 403)
                    for bad in ({'question': 'Q?'}, {'question': 'Q?', 'answer': ''}, {'question': 'Q?', 'answer': 'x' * 301}, {'question': 'Q?', 'answer': 'No', 'job': 1}):
                        self.assertEqual((await client.post('/api/jobs/answers', json=bad)).status_code, 400, bad)
                    reply = (await client.post('/api/jobs/answers', json={'question': 'Will you sign a 2 year bond?', 'answer': 'No'})).json()
                    self.assertEqual(reply['questions'], []); self.assertEqual(reply['answers'][0]['answer'], 'No')
                    reply = (await client.post('/api/jobs/answers/forget', json={'key': reply['answers'][0]['key']})).json()
                    self.assertEqual(reply['answers'], [])
                    self.assertEqual((await client.post('/api/jobs/answers/forget', json={'key': 5})).status_code, 400)

if __name__ == '__main__':
    unittest.main()
