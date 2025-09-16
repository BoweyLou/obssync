# Edge Case Test File for Task Parsing

This file contains various edge cases to test the task parsing robustness.

## Regular Tasks
- [ ] Basic task ^t-5bfc6533712a
- [x] Completed task ^t-569965e873fd
- [x] Task with ^t-e04c2c2686f7
- [ ] Task with block ID ^test-block-1

## Indented Tasks (Nested Lists)
- [ ] Level 1 task ^t-481e07dc147c
- [ ] Another level 1 task ^t-31048aab68bb

## Mixed List Types
1. [ ] Numbered list with task checkbox
2. Regular numbered item
   - [ ] Nested task under numbered item ^t-a26057125224
3. [ ] Another numbered task

## Tasks in Different Contexts

### In Quote Blocks
> - [ ] Task in quote block
> - [x] Completed task in quote

### In Code Blocks (Should NOT be parsed as tasks)
```markdown
- [ ] This should not be parsed as a task
- [x] Neither should this
```

```
- [ ] Code block task (should be ignored)
```

    - [ ] Indented code block task ^t-7a7a6bc16d26

### Tasks with Complex Content
- [ ] Task with "quotes" and 'apostrophes' ^t-31eaf17d37a9
- [ ] Task with <brackets> and [square brackets] ^t-fb5509613fb5
- [ ] Task with 🔁 every day ⏫ priority ^t-526740979877
- [ ] Task with ✅ 2025-01-01 done date ^completed-block

## Unicode and Special Characters
- [ ] Task with émojis 🎉 and ünïcödé characters ^t-3ebbbb73b4b6
- [ ] Task with symbols: ™ © ® £ € ¥ § ¶ ^t-77f4be3ed95e
- [ ] Task with math: x² + y² = z² and α + β = γ ^t-3db711d8ddc1

## Malformed Tasks (Should NOT match)
- [] Missing space in checkbox
- [y] Invalid status character
- [!] Alternative status (not in our regex)
- [?] Question status
- [-] Cancelled status
-[ ] Missing space after dash
* [] Missing space in asterisk task

## Long Tasks
- [ ] This is an extremely long task description that goes on and on and on and should test how well the parser handles very lengthy content that might span what feels like multiple lines but is actually just one very long line with lots of text ^t-220f3127c4cd
- [ ] Another long task with 📅 2025-12-31 and #verylongtagnamethatmightcauseproblemswithparsing and 🔁 every single day ⏫ and lots of other metadata that should all be parsed correctly ^very-long-block-id-that-tests-limits

## Edge Cases with Whitespace
- [ ]		Task with tabs ^t-34f0a77ace89
- [ ]   Task with multiple spaces ^t-b38e140c4849
- [ ] 	Mixed tabs and spaces ^t-edfbcafe8370
- [ ] Trailing whitespace task ^t-cc0e107f671f
- [x] ^t-ea28535fd95c

## Tasks with Links and References
- [ ] Task with [[internal link]] ^t-da909e97273e
- [ ] Task with [external link](https://example.com) ^t-bb0162620a03
- [ ] Task with ![[embedded image]] ^t-630b09014f32
- [ ] Task referencing [[other file#section]] ^t-8ec5ef14204d

## Mixed with Other Markdown
# Heading 1
- [ ] Task under heading 1 ^t-8d80d2e11ac2

## Heading 2
- [x] Completed under heading 2 ^t-4936c6d4851d

Some paragraph text here.

- [ ] Task after paragraph ^t-a3081de94bac
- [ ] Another task ^t-2eac7bb6ece9

**Bold text**
- [ ] Task after bold ^t-bc0ec59be890

*Italic text*
- [ ] Task after italic ^t-e4c746e3a197

---

- [ ] Task after horizontal rule ^t-8a40cf04f22a

| Table | Header |
|-------|--------|
| Cell  | - [ ] Task in table |
| Data  | - [x] Completed in table |

- [ ] Task after table ^t-764eab61a5c0
