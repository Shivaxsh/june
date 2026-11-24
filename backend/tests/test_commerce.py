"""Offline commerce: approval-bound, atomic and idempotent fake merchants."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from june.integrations import create_tools


class CommerceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.commerce import Commerce, register
        self.tmp=tempfile.TemporaryDirectory()
        self.plans=create_tools(Path(self.tmp.name),None)
        self.service=Commerce(Path(self.tmp.name),self.plans)
        register(self.plans,self.service)
        self.n=0

    async def asyncTearDown(self):
        await self.plans.close();self.tmp.cleanup()

    async def say(self,text,chat='fixture-chat'):
        self.n+=1
        return await self.service.respond(f'commerce-{self.n:04}',chat,text)

    async def ready(self,domain='retail'):
        prompts={'retail':['buy headphones','Noida','1000','tomorrow'],
                 'tickets':['book movie tickets','Synthetic Movie','Noida','tomorrow','7pm','2','1000','choose for me'],
                 'dining':['book a restaurant table','Noida','tomorrow','7pm','2','choose for me']}
        for text in prompts[domain]:reply=await self.say(text)
        self.assertEqual(reply['transaction']['status'],'choosing',reply)
        return await self.say('choose 1')

    async def approve(self,reply):
        plan=reply['plan']
        await self.plans.approve(plan['id'],dict(requestId=f'approve-{self.n:04}',revision=plan['revision'],fingerprint=plan['fingerprint']))
        for _ in range(100):
            p=(await self.plans.get(plan['id']))['plan']
            if p['status'] not in ('approved','running'):return p
            await asyncio.sleep(.01)
        self.fail('plan did not finish')

    async def test_all_three_domains_require_review_and_return_simulated_receipts(self):
        for domain in ('retail','tickets','dining'):
            with self.subTest(domain=domain):
                quote=await self.ready(domain)
                self.assertIsNone(quote['transaction']['receipt'])
                self.assertFalse(quote['plan']['rememberable'])
                done=await self.approve(quote)
                self.assertEqual(done['status'],'completed')
                receipt=self.service.get(quote['transaction']['id'])['receipt']
                self.assertTrue(receipt['simulated'])
                if domain=='dining':self.assertEqual(receipt['totalMinor'],0)
                self.assertEqual((await self.service.commit(quote['transaction']['id'],quote['transaction']['quote']['fingerprint']))['verified'],True)
                self.assertEqual(self.service.get(quote['transaction']['id'])['receipt']['id'],receipt['id'])

    async def test_changed_quote_cannot_be_committed_by_old_approval(self):
        quote=await self.ready()
        self.service.merchant.price_delta=100
        done=await self.approve(quote)
        self.assertNotEqual(done['status'],'completed')
        self.assertIsNone(self.service.get(quote['transaction']['id'])['receipt'])

    async def test_ordinary_go_ahead_never_executes_without_bound_review(self):
        await self.ready()
        for text in ('I approve','go ahead','yes book it','okay'):
            reply=await self.say(text)
            self.assertIsNone(reply['transaction']['receipt'])

    async def test_secret_is_rejected_before_persisting(self):
        from june.errors import JuneError
        with self.assertRaises(JuneError):await self.say('my card number is 4111 1111 1111 1111')
        self.assertNotIn('4111',self.service.path.read_bytes().decode(errors='ignore'))

    async def test_structured_selection_is_current_and_idempotent(self):
        from june.errors import JuneError
        await self.say('buy milk');await self.say('Noida');await self.say('1000');r=await self.say('tomorrow')
        offer=r['transaction']['offers'][0]['id']
        selected=await self.service.respond('select-offer-0001','fixture-chat',select={'offerId':offer})
        again=await self.service.respond('select-offer-0001','fixture-chat',select={'offerId':offer})
        self.assertEqual(selected['plan']['id'],again['plan']['id'])
        with self.assertRaises(JuneError):await self.service.respond('select-offer-0002','fixture-chat',select={'offerId':offer})

    async def test_unknown_commit_checks_receipt_without_a_second_effect(self):
        quote=await self.ready();self.service.merchant.unknown_after_commit=True
        done=await self.approve(quote);self.assertEqual(done['status'],'unknown')
        t=self.service.get(quote['transaction']['id']);rid=t['receipt']['id']
        await self.say('check receipt')
        self.assertEqual(self.service.get(t['id'])['status'],'completed')
        await self.service.commit(t['id'],t['quote']['fingerprint'])
        self.assertEqual(self.service.get(t['id'])['receipt']['id'],rid)

    async def test_correction_invalidates_old_plan_and_preferences_need_explicit_request(self):
        quote=await self.ready('tickets');pid=quote['plan']['id']
        corrected=await self.say('make it 3 people')
        self.assertEqual(corrected['transaction']['slots']['partySize'],3)
        self.assertIsNone(corrected['transaction']['quote'])
        self.assertEqual((await self.plans.get(pid))['plan']['status'],'cancelled')
        self.assertEqual(self.service.state()['preferences'],{})
        await self.say('remember my area as Noida')
        self.assertEqual(self.service.state()['preferences']['area'],'Noida')
        await self.say('forget my area')
        self.assertEqual(self.service.state()['preferences'],{})

    async def test_cancellation_requires_its_own_review(self):
        quote=await self.ready();await self.approve(quote)
        review=await self.say('cancel the order')
        self.assertEqual(review['transaction']['receipt']['status'],'confirmed')
        done=await self.approve(review)
        self.assertEqual(done['status'],'completed')
        self.assertEqual(self.service.get(quote['transaction']['id'])['receipt']['status'],'cancelled')

    async def test_expired_and_sold_out_quotes_never_commit(self):
        for mode in ('expired','sold-out'):
            quote=await self.ready();tid=quote['transaction']['id']
            if mode=='expired':
                t=self.service.get(tid);t['quote']['expiresAt']=1;self.service.save(t)
            else:self.service.merchant.sold_out=True
            done=await self.approve(quote)
            self.assertNotEqual(done['status'],'completed');self.assertIsNone(self.service.get(tid)['receipt'])
            self.service.merchant.sold_out=False

    async def test_spoken_numbers_and_unrelated_chat_stays_unrelated(self):
        await self.say('buy milk');await self.say('Noida')
        reply=await self.say('one thousand rupees')
        self.assertEqual(reply['transaction']['slots']['budgetMinor'],100000)
        self.assertFalse(self.service.handles('what is the capital of France','fixture-chat'))
        self.assertFalse(self.service.handles('tell me about stars','other-chat'))

    async def test_fixture_stock_is_shared_and_cancellation_releases_it(self):
        first=await self.ready();await self.approve(first)
        for _ in range(2):
            q=await self.ready();await self.approve(q)
        await self.say('buy headphones');await self.say('Noida');await self.say('1000');out=await self.say('tomorrow')
        self.assertEqual(out['transaction']['offers'],[])
        q=await self.ready('dining');await self.approve(q)
        self.assertEqual(self.service.get(q['transaction']['id'])['receipt']['totalMinor'],0)

    async def test_review_never_speaks_an_approval_phrase_and_seat_map_is_truthful(self):
        from june.commerce import APPROVAL
        for domain in ('retail','tickets','dining'):
            q=await self.ready(domain)
            self.assertIsNone(APPROVAL.search(q['transaction']['quote']['summary']))
            if domain=='tickets':
                offer=q['transaction']['offers'][0]
                selected=[seat['id'] for row in offer['seatMap']['rows'] for seat in row['seats'] if seat['status']=='selected']
                self.assertEqual(selected,offer['seats'])
                self.assertEqual(len(selected),2)

    async def test_booking_does_not_swallow_music_commands_or_general_questions(self):
        await self.say('book movie tickets')
        for text in ('play some music','change the song','what is the weather','tell me about stars'):
            self.assertFalse(self.service.handles(text,'fixture-chat'),text)
        q=await self.ready('tickets')
        self.assertFalse(self.service.handles('change the song','fixture-chat'))
        self.assertTrue(self.service.handles('change location to Delhi','fixture-chat'))

    async def test_inline_spoken_numbers_are_not_asked_for_twice(self):
        dining=await self.say('reserve a table for two people in Noida tomorrow at 8 pm, you choose','spoken-dining')
        self.assertEqual(dining['transaction']['status'],'choosing')
        self.assertEqual(dining['transaction']['slots']['partySize'],2)
        retail=await self.say('buy two milk in Noida tomorrow under two hundred rupees','spoken-retail')
        self.assertEqual(retail['transaction']['status'],'choosing')
        self.assertEqual(retail['transaction']['slots']['quantity'],2)
        self.assertEqual(retail['transaction']['slots']['budgetMinor'],20000)

    async def test_vague_dining_request_does_not_become_its_own_location(self):
        first=await self.say('book a restaurant table')
        self.assertNotIn('area',first['transaction']['slots'])
        answer=await self.say('Noida')
        self.assertEqual(answer['transaction']['slots']['area'],'Noida')

    async def test_spoken_reviews_use_readable_dates_and_no_receipt_hash(self):
        quote=await self.ready()
        summary=quote['transaction']['quote']['summary']
        self.assertNotIn('Asia/Kolkata',summary)
        self.assertNotRegex(summary,r'\d{4}-\d{2}-\d{2}')
        await self.approve(quote)
        cancel=await self.say('cancel the order')
        self.assertNotIn(cancel['transaction']['receipt']['id'],cancel['reply'])
        self.assertIn('Sim Mart',cancel['reply'])

    async def test_conditional_approval_stays_app_owned_and_voids_the_old_review(self):
        quote=await self.ready()
        text='go ahead but make it cheaper'
        self.assertTrue(self.service.handles(text,'fixture-chat'))
        result=await self.say(text)
        self.assertIsNone(result['transaction']['receipt'])
        self.assertIsNone(result['transaction']['quote'])
        self.assertEqual((await self.plans.get(quote['plan']['id']))['plan']['status'],'cancelled')

    async def test_acknowledgements_reread_the_exact_quote_without_general_model_or_execution(self):
        for phrase in ('Go ahead, June.','yeah go for it','sounds good','do it','perfect, thanks','read the quote again'):
            with self.subTest(phrase=phrase):
                quote=await self.ready()
                self.assertTrue(self.service.handles(phrase,'fixture-chat'))
                reply=await self.say(phrase)
                self.assertEqual(reply['plan']['id'],quote['plan']['id'])
                self.assertEqual(reply['plan']['status'],'proposed')
                self.assertIn(quote['plan']['steps'][0]['preview'],reply['reply'])
                self.assertIsNone(reply['transaction']['receipt'])

    async def test_common_speech_transcripts_accept_word_hours_and_dotted_meridiems(self):
        for phrase in ('at eight p.m.','at 8 p. m.','at eight pm'):
            t=await self.say('reserve a table for two people in Noida tomorrow '+phrase+', you choose','hours-'+str(self.n))
            self.assertEqual(t['transaction']['slots'].get('time'),'20:00',phrase)

    async def test_unmatched_venue_never_poisons_delegation_or_first_choice(self):
        for text in ('reserve a table','Noida','tomorrow','8pm','2'):
            reply=await self.say(text)
        unclear=await self.say('purple umbrella')
        self.assertNotIn('venue',unclear['transaction']['slots'])
        recovered=await self.say('choose for me')
        self.assertEqual(recovered['transaction']['status'],'choosing')
        self.assertTrue(recovered['transaction']['offers'])
        self.assertTrue(self.service.handles('The first one.','fixture-chat'))
        selected=await self.say('The first one.')
        self.assertEqual(selected['plan']['status'],'proposed')

    async def test_delegation_can_recover_legacy_empty_offer_state(self):
        quote=await self.ready('dining');t=quote['transaction']
        await self.service.invalidate(t)
        t.update(status='choosing',offers=[]);t['slots']['venue']='unmatched fixture name';self.service.save(t)
        result=await self.say('choose for me')
        self.assertTrue(result['transaction']['offers'])
        self.assertEqual(result['transaction']['slots']['venue'],'choose for me')


class PartySizeAsSpoken(unittest.IsolatedAsyncioTestCase):
    """"Book a table for two" must not be followed by "How many people?"; "i said two" is an answer, not small talk."""
    async def asyncSetUp(self):
        from june.commerce import Commerce, register
        self.tmp=tempfile.TemporaryDirectory()
        self.plans=create_tools(Path(self.tmp.name),None)
        self.service=Commerce(Path(self.tmp.name),self.plans); register(self.plans,self.service); self.n=0

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def say(self,text,chat='party-chat'):
        self.n+=1
        return await self.service.respond(f'commerce-{self.n:04}',chat,text)

    async def test_party_size_in_the_opening_request(self):
        for i,(opening,size) in enumerate((('Hey Jun, book a table for two tomorrow at 8pm.',2),('book a table for 2 tomorrow at 8 pm',2),
                                           ('table for two in Noida tomorrow at 8pm',2),('reserve a table, party of three, tomorrow 7 pm',3),
                                           ('book a table for us, four of us, tomorrow at 9 pm',4),('reserve a table for 5 guests tomorrow at 8 pm',5))):
            with self.subTest(opening=opening):
                reply=await self.say(opening,chat=f'open-{i}')
                self.assertEqual(reply['transaction']['domain'],'dining')
                self.assertEqual(reply['transaction']['slots'].get('partySize'),size)
                self.assertNotIn('partySize',reply['transaction']['missing'])

    async def test_a_time_is_never_a_party_size(self):
        reply=await self.say('book a table for 8 pm tomorrow')
        self.assertNotIn('partySize',reply['transaction']['slots'])
        self.assertEqual(reply['transaction']['slots'].get('time'),'20:00')

    async def test_spoken_answers_to_how_many_people(self):
        for i,(answer,size) in enumerate((('i said two',2),('two',2),('We are 4.',4),('just two of us',2),('three people please',3),('no, two',2))):
            chat=f'answer-{i}'
            with self.subTest(answer=answer):
                await self.say('book a table in Noida tomorrow at 8 pm',chat=chat)
                self.assertTrue(self.service.handles(answer,chat),'a party-size answer goes to the booking, never to the model')
                reply=await self.say(answer,chat=chat)
                self.assertEqual(reply['transaction']['slots'].get('partySize'),size)

    async def test_unrelated_number_questions_still_go_to_the_model(self):
        await self.say('book a table in Noida tomorrow at 8 pm')
        self.assertFalse(self.service.handles('what is two plus two','party-chat'))


class SpokenAnswersAreUnderstood(unittest.IsolatedAsyncioTestCase):
    """The 2026-11-22 hands-free booking: "Noida" heard as "Night", "choose for me" heard as "choose from me"."""
    async def asyncSetUp(self):
        from june.commerce import Commerce, register
        self.tmp=tempfile.TemporaryDirectory()
        self.plans=create_tools(Path(self.tmp.name),None)
        self.service=Commerce(Path(self.tmp.name),self.plans); register(self.plans,self.service); self.n=0

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def flow(self,lines,chat):
        replies=[]
        for line in lines:
            self.n+=1; replies.append(await self.service.respond(f'commerce-{self.n:04}',chat,line))
        return replies

    async def test_a_common_word_is_not_accepted_as_the_city(self):
        r=await self.flow(['book a table for two tomorrow at 8 p.m.','Night.'],'night')
        self.assertNotIn('area',r[-1]['transaction']['slots'])
        self.assertIn('I heard “Night”. Which city or locality is that?',r[-1]['reply'])
        r=await self.flow(['Noida'],'night')
        self.assertEqual(r[-1]['transaction']['slots']['area'],'Noida')

    async def test_places_are_accepted_and_near_misses_snap_to_known_cities(self):
        for i,(said,area) in enumerate((('Noyda','Noida'),('in Gurgaon','Gurgaon'),('Sector 62 Noida','Sector 62 Noida'),('Kanpur','Kanpur'),('I said Delhi','Delhi'))):
            with self.subTest(said=said):
                r=await self.flow(['book a table for two tomorrow at 8 p.m.',said],f'place-{i}')
                self.assertEqual(r[-1]['transaction']['slots'].get('area'),area)

    async def test_choose_for_me_in_every_natural_form_shows_the_options(self):
        for i,said in enumerate(('Choose from me.','I said, choose for me.','you pick','any is fine','whatever','surprise me','up to you','your choice')):
            with self.subTest(said=said):
                r=await self.flow(['book a table for two tomorrow at 8 p.m.','Noida',said],f'choose-{i}')
                self.assertEqual(r[-1]['transaction']['slots'].get('venue'),'choose for me')
                self.assertEqual(r[-1]['transaction']['status'],'choosing')

    async def test_a_part_of_a_venue_name_selects_it_and_an_unknown_one_asks_again(self):
        r=await self.flow(['book a table for two tomorrow at 8 p.m.','Noida','table garden'],'venue-a')
        self.assertEqual(r[-1]['transaction']['slots'].get('venue'),'Sim Table Garden')
        r=await self.flow(['book a table for two tomorrow at 8 p.m.','Noida','the pizza place'],'venue-b')
        self.assertNotIn('venue',r[-1]['transaction']['slots'])


class ContinuationBeforeAQuote(unittest.IsolatedAsyncioTestCase):
    """2026-11-23: "proceed" while options were shown went to the model, which falsely said it can't book."""
    WORDS = ('proceed','Proceed.','continue','go on','okay','yes','yeah, go ahead','next','do it','book it','okay, proceed please','sounds good')

    async def asyncSetUp(self):
        from june.commerce import Commerce, register
        self.tmp=tempfile.TemporaryDirectory()
        self.plans=create_tools(Path(self.tmp.name),None)
        self.service=Commerce(Path(self.tmp.name),self.plans); register(self.plans,self.service); self.n=0

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def say(self,text,chat):
        self.n+=1
        return await self.service.respond(f'commerce-{self.n:04}',chat,text)

    async def test_while_choosing_continuation_asks_which_option_and_never_commits(self):
        for i,word in enumerate(self.WORDS):
            chat=f'choosing-{i}'
            with self.subTest(word=word):
                await self.say('book a table for two people in Noida at 8pm tomorrow.',chat)
                shown=await self.say('choose for me',chat)
                self.assertEqual(shown['transaction']['status'],'choosing')
                self.assertTrue(self.service.handles(word,chat),'answered by commerce, never the model')
                reply=await self.say(word,chat)
                self.assertEqual(reply['transaction']['status'],'choosing')
                self.assertIsNone(reply['transaction']['planId']); self.assertIsNone(reply['transaction']['receipt'])
                self.assertEqual(reply['reply'],'Simulation: Tell me the number of the option you want.')
                self.assertNotRegex(reply['reply'].lower(),r'first one|second one|choose for me','never the answer words the echo matcher rejects')
                self.assertNotRegex(reply['reply'].lower(),r'go ahead|book it|place the order|i approve','no approval phrase in the prompt (echo safety)')
                chosen=await self.say('the first one',chat)
                self.assertIn(chosen['transaction']['status'],('quoted','awaiting-approval'),'a real choice still works afterwards')

    async def test_while_collecting_continuation_repeats_the_missing_question(self):
        for i,word in enumerate(('proceed','okay','yes, continue')):
            chat=f'collecting-{i}'
            with self.subTest(word=word):
                await self.say('book a table for two tomorrow at 8 pm',chat)
                self.assertTrue(self.service.handles(word,chat))
                reply=await self.say(word,chat)
                self.assertEqual(reply['transaction']['status'],'collecting')
                self.assertIn('Which city and locality',reply['reply'])

    async def test_quoted_approval_rules_are_unchanged(self):
        await self.say('book a table for two people in Noida at 8pm tomorrow.','q')
        await self.say('choose for me','q'); quoted=await self.say('the first one','q')
        self.assertIn(quoted['transaction']['status'],('quoted','awaiting-approval'))
        self.assertTrue(self.service.handles('yeah, go ahead','q'))
        self.assertFalse(self.service.handles('what is two plus two','q'))


class LowInformationChoiceReplies(unittest.IsolatedAsyncioTestCase):
    """2026-11-23 live: options were shown, the next transcript was "Television.", the model said it cannot book."""
    async def asyncSetUp(self):
        from june.commerce import Commerce, register
        self.tmp=tempfile.TemporaryDirectory()
        self.plans=create_tools(Path(self.tmp.name),None)
        self.service=Commerce(Path(self.tmp.name),self.plans); register(self.plans,self.service); self.n=0

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def say(self,text,chat):
        self.n+=1
        return await self.service.respond(f'commerce-{self.n:04}',chat,text)

    async def options(self,chat):
        await self.say('book a table for two people in Noida at 8pm tomorrow.',chat)
        shown=await self.say('choose for me',chat)
        self.assertEqual(shown['transaction']['status'],'choosing')

    async def test_unusable_short_replies_ask_which_option_and_select_nothing(self):
        for i,said in enumerate(('Television.','Hmm.','Paper.','Joe is funny.','the garden one','thanks')):
            chat=f'low-{i}'
            with self.subTest(said=said):
                await self.options(chat)
                self.assertTrue(self.service.handles(said,chat),'answered in the booking, never by the model')
                reply=await self.say(said,chat)
                self.assertEqual(reply['reply'],'Simulation: I didn’t catch which option. Tell me the number of the option you want.')
                self.assertNotRegex(reply['reply'].lower(),r'first one|second one|choose for me','never the answer words the echo matcher rejects')
                t=reply['transaction']
                self.assertEqual(t['status'],'choosing'); self.assertIsNone(t['planId']); self.assertIsNone(t['quote']); self.assertIsNone(t['receipt'])
                self.assertNotRegex(reply['reply'].lower(),r'go ahead|book it|place the order|i approve')
                chosen=await self.say('the second one',chat)
                self.assertIn(chosen['transaction']['status'],('quoted','awaiting-approval'),'a real choice still works next')

    async def test_questions_commands_and_understood_changes_keep_their_handlers(self):
        await self.options('keep')
        for said in ('what is the weather today','What is two plus two?','Is it open late?','play some music','open Chrome','tell me a joke','Dinner nearby?','Television?'):
            with self.subTest(said=said):
                self.assertFalse(self.service.handles(said,'keep'),'genuine questions and commands stay available')
        for said in ('cheaper','second','option two','choose for me','different venue'):
            with self.subTest(said=said):
                self.assertTrue(self.service.handles(said,'keep'))
        self.assertNotIn('I didn’t catch',(await self.say('cheaper','keep'))['reply'])

    async def test_outside_choosing_nothing_changes(self):
        await self.say('book a table for two tomorrow at 8 pm','collect')
        reply=await self.say('Television.','collect')  # an area answer: asked again by place_answer, not by this rule
        self.assertNotIn('which option',reply['reply'])


class LowInformationKeepsQuestionMarks(unittest.TestCase):
    def test_the_original_punctuation_decides(self):
        from june.commerce import low_information_choice
        self.assertFalse(low_information_choice('Dinner nearby?'), 'a short question stays a question')
        self.assertTrue(low_information_choice('Dinner nearby.'))
        self.assertTrue(low_information_choice('Television.'))


class OptionListPromptIsEchoSafe(unittest.IsolatedAsyncioTestCase):
    async def test_the_option_list_asks_for_a_number_without_repeating_answer_words(self):
        from june.commerce import Commerce, register
        with tempfile.TemporaryDirectory() as tmp:
            plans=create_tools(Path(tmp),None); service=Commerce(Path(tmp),plans); register(plans,service)
            try:
                await service.respond('commerce-0001','opts','book a table for two people in Noida at 8pm tomorrow.')
                shown=await service.respond('commerce-0002','opts','choose for me')
                self.assertTrue(shown['reply'].endswith('Tell me the number of the option you want.'))
                self.assertNotRegex(shown['reply'].lower(),r'choose \d|first one|second one|choose for me')
                picked=await service.respond('commerce-0003','opts','choose 1')
                self.assertIn(picked['transaction']['status'],('quoted','awaiting-approval'),'"choose 1" still selects')
            finally:
                await plans.close()
