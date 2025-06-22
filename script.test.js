import { roundDateToEndOfMonth } from './script.js';

describe('roundDateToEndOfMonth', () => {
    test('should round a mid-month date to the end of that month', () => {
        const inputDate = '2023-05-15';
        const expectedDate = '2023-05-31';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle the end of a month correctly', () => {
        const inputDate = '2023-02-28';
        const expectedDate = '2023-02-28';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle the beginning of a month correctly', () => {
        const inputDate = '2023-09-01';
        const expectedDate = '2023-09-30';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle a leap year correctly', () => {
        const inputDate = '2024-02-10';
        const expectedDate = '2024-02-29';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should return null for an invalid date string', () => {
        const inputDate = 'not a real date';
        expect(roundDateToEndOfMonth(inputDate)).toBeNull();
    });
}); 