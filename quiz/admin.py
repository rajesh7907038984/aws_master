from django.contrib import admin
from .models import Quiz, Question, Answer, QuizAttempt, UserAnswer, QuizGradeOverride, QuizTag
import json

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 4
    fields = ('answer_text', 'is_correct', 'answer_order', 'learning_style')

class QuestionAdmin(admin.ModelAdmin):
    inlines = [AnswerInline]
    list_display = ('question_text', 'quiz', 'question_type', 'points', 'order')
    list_filter = ('quiz', 'question_type')
    search_fields = ('question_text',)

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    show_change_link = True

class QuizAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    list_display = ('title', 'creator', 'time_limit', 'passing_score', 'is_active', 'created_at')
    list_filter = ('creator', 'is_active')
    search_fields = ('title', 'description')

class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ('question', 'answer', 'text_answer', 'matching_answers', 'is_correct', 'display_answer_details')
    fields = ('question', 'display_answer_details', 'is_correct', 'points_earned')
    
    def display_answer_details(self, obj):
        """Return a formatted display of the user's answer based on question type"""
        if obj.question.question_type == 'multiple_select':
            # Use the new helper method to get selected options
            selected_options = obj.get_selected_options_for_admin()
            
            # Get correct answers for comparison
            correct_ids = obj.question.get_correct_answers()
            correct_answers = Answer.objects.filter(id__in=correct_ids)
            correct_texts = [a.answer_text for a in correct_answers]
            correct_display = f"correct answer: {', '.join(correct_texts)}"
            
            if selected_options:
                # Format user's selected answers
                selected_texts = [option.answer_text for option in selected_options]
                selected_display = f"selected answer: {', '.join(selected_texts)}"
                
                # Check correctness
                selected_ids = [str(option.id) for option in selected_options]
                is_fully_correct = set(selected_ids) == set(str(id) for id in correct_ids)
                
                # Update record if correctness doesn't match
                if is_fully_correct != obj.is_correct:
                    print(f"Warning: Multiple select answer correctness mismatch for question {obj.question_id}. " 
                          f"Calculated={is_fully_correct}, Stored={obj.is_correct}. "
                          f"User answers={selected_ids}, Correct answers={correct_ids}")
                    obj.is_correct = is_fully_correct
                    obj.points_earned = obj.question.points if is_fully_correct else 0
                    obj.save(update_fields=['is_correct', 'points_earned'])
                
                status = "<span style='color:green'>✓ Correct</span>" if is_fully_correct else "<span style='color:red'>✗ Incorrect</span>"
                return f"{selected_display}<br>{correct_display}<br>{status}"
            else:
                # No valid options selected
                return f"No answer selected<br>{correct_display}"
        elif obj.question.question_type in ['multiple_choice', 'true_false']:
            if not obj.answer:
                # Get the correct answer
                correct_answer = obj.question.answers.filter(is_correct=True).first()
                if correct_answer:
                    return f"No answer selected<br>correct answer: {correct_answer.answer_text}"
                return "No answer"
            
            # Get the correct answer
            correct_answer = obj.question.answers.filter(is_correct=True).first()
            
            # Format in the requested style
            selected_display = f"selected answer: {obj.answer.answer_text}"
            correct_display = f"correct answer: {correct_answer.answer_text if correct_answer else 'Unknown'}"
            
            # Add status indicator
            status = "<span style='color:green'>✓ Correct</span>" if obj.is_correct else "<span style='color:red'>✗ Incorrect</span>"
            
            return f"{selected_display}<br>{correct_display}<br>{status}"
            
        elif obj.question.question_type == 'fill_blank':
            return obj.text_answer or "No answer"
            
        elif obj.question.question_type == 'multi_blank':
            if obj.text_answer:
                try:
                    blank_answers = json.loads(obj.text_answer)
                    # Get the number of blanks in the question
                    blanks_count = obj.question.answers.count()
                    # Format output
                    items = []
                    for i, answer in enumerate(blank_answers):
                        blank_number = i + 1
                        items.append(f"Blank #{blank_number}: {answer}")
                    return "<br>".join(items)
                except (json.JSONDecodeError, ValueError):
                    return f"Error parsing: {obj.text_answer}"
            return "No answer"
            
        elif obj.question.question_type == 'matching':
            if obj.matching_answers:
                try:
                    pairs = []
                    for pair in obj.matching_answers:
                        pairs.append(f"{pair.get('left_item')} → {pair.get('right_item')}")
                    return "<br>".join(pairs)
                except Exception as e:
                    return f"Error parsing: {e}"
            return "No answer"
            
        return obj.text_answer or (obj.answer.answer_text if obj.answer else "No answer")
        
    display_answer_details.short_description = "User's Answer"
    display_answer_details.allow_tags = True

class QuizAttemptAdmin(admin.ModelAdmin):
    inlines = [UserAnswerInline]
    list_display = ('user', 'quiz', 'score', 'is_completed', 'start_time', 'end_time')
    list_filter = ('quiz', 'user', 'is_completed')
    search_fields = ('quiz__title', 'user__username')
    readonly_fields = ('score',)
    
    def get_object(self, request, object_id, from_field=None):
        """Override get_object to create placeholder answers for missing questions"""
        obj = super().get_object(request, object_id, from_field)
        if obj:
            # Get all questions for this quiz
            questions = obj.quiz.questions.all()
            # Get existing answers
            existing_answers = obj.user_answers.all()
            existing_question_ids = [answer.question_id for answer in existing_answers]
            
            # Create placeholder answers for questions without answers
            for question in questions:
                if question.id not in existing_question_ids:
                    # Create a placeholder answer that won't be saved to the database
                    UserAnswer.objects.create(
                        attempt=obj,
                        question=question,
                        is_correct=False,
                        points_earned=0
                    )
        return obj

class AnswerAdmin(admin.ModelAdmin):
    list_display = ('answer_text', 'question', 'is_correct', 'answer_order')
    list_filter = ('question__quiz', 'is_correct')
    search_fields = ('answer_text', 'question__question_text')
    ordering = ('question', 'answer_order')

class QuizGradeOverrideAdmin(admin.ModelAdmin):
    list_display = ('quiz_attempt', 'original_score', 'override_score', 'override_by', 'created_at')
    list_filter = ('override_by',)
    search_fields = ('quiz_attempt__user__username', 'quiz_attempt__quiz__title', 'override_reason')

class QuizTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(QuizAttempt, QuizAttemptAdmin)
admin.site.register(Answer, AnswerAdmin)
admin.site.register(QuizGradeOverride, QuizGradeOverrideAdmin)
admin.site.register(QuizTag, QuizTagAdmin)
