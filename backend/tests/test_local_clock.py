import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from june.app_info import application_reply

class LocalClock(unittest.TestCase):
    def test_current_date_month_year_and_time_are_application_owned(self):
        instant=datetime(2026,11,13,23,59,tzinfo=ZoneInfo('Asia/Kolkata'))
        for question,expected in (("What's today's date?",'13 November 2026'),
                ('Can you tell me what date is today?','13 November 2026'),
                ('What month is today?','November'),('What year is it?','2026'),
                ('What time is it?','23:59'),('What day is it today?','Friday'),
                ('Which day is it today?','Friday'),('What month is it now?','November'),
                ('Whats the date tomorrow?','14 November 2026'),('What day is tomorrow?','Saturday')):
            with self.subTest(question=question),patch('june.app_info.local_now',return_value=instant,create=True):
                answer=application_reply('fixture',question,False)
                self.assertIsNotNone(answer)
                self.assertIn(expected,answer)
    def test_negative_app_instruction_does_not_hide_a_clock_question(self):
        instant=datetime(2026,11,20,19,10,tzinfo=ZoneInfo('Asia/Kolkata'))
        for question in ('Do not open any apps. What time is it?', "Don't launch applications; what time is it?", 'Do not open apps. What date is today?'):
            with self.subTest(question=question), patch('june.app_info.local_now',return_value=instant):
                answer=application_reply('fixture',question,False)
                self.assertIsNotNone(answer)
                self.assertIn('19:10' if 'time' in question else '20 November 2026',answer)

    def test_other_dates_quotations_and_compound_tasks_are_not_clock_questions(self):
        for question in ('When is Diwali 2027?', 'What date is on my invoice?',
                         'Translate "what time is it" into Hindi.', 'What time is it and explain RAM?',
                         'Do not open apps. What time is it and explain RAM?',
                         'Translate "Do not open apps. What time is it?" into Hindi.'):
            self.assertIsNone(application_reply('fixture',question,False),question)

    def test_spoken_and_hinglish_forms_of_the_time_and_date_questions(self):
        # How Whisper actually writes these from speech, plus Hinglish typing. Fixture clock only.
        instant=datetime(2026,11,22,20,5,tzinfo=ZoneInfo('Asia/Kolkata'))
        for question,expected in (('what time it is.','20:05'),('What time it is now?','20:05'),('Tell me the time.','20:05'),
                                  ("What's the time?",'20:05'),('What time is it right now?','20:05'),('Current time please','20:05'),
                                  ('Time please.','20:05'),('Hey June, what time it is?','20:05'),('Can you tell me the current time?','20:05'),
                                  ('time kya hai','20:05'),('kya time hai abhi','20:05'),('kitne baje hain','20:05'),
                                  ("Today's date?",'22 November 2026'),('What date is it?','22 November 2026'),
                                  ('What day it is.','Sunday'), ('I am asking what day it is.','Sunday'),
                                  ('I am saying, I am asking what day it is.','Sunday'),
                                  ("I'm asking you what date it is today.",'22 November 2026'),
                                  ('I mean, what time is it?','20:05'),
                                  ('aaj kya date hai','22 November 2026'),('aaj kaun sa din hai','Sunday')):
            with self.subTest(question=question),patch('june.app_info.local_now',return_value=instant,create=True):
                answer=application_reply('fixture',question,False)
                self.assertIsNotNone(answer,question)
                self.assertIn(expected,answer)

    def test_other_time_questions_are_not_the_clock(self):
        for question in ('What time does the shop open?','What time is the movie?','What time is it in London?','Set a timer for five minutes.',
                         'I am asking what day it is in London.', 'I mean what day it is and explain RAM.',
                         'What time zone am I in?','Time.','time for me','What time should I sleep?','How much time is left?','What day is Diwali?'):
            answer=application_reply('fixture',question,False) or ''
            self.assertNotIn('The time on this Mac',answer,question); self.assertNotIn('On this Mac,',answer,question)
