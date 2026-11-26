import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

// Popular KTU engineering colleges and polytechnics. ComboInput stays free-text
// so an attendee whose institution is missing can simply type it.
export const COLLEGE_SUGGESTIONS = [
  'NSS College of Engineering, Palakkad',
  'College of Engineering Trivandrum (CET)',
  'Government Engineering College, Thrissur',
  'Government Engineering College, Sreekrishnapuram',
  'Government Engineering College, Barton Hill, Thiruvananthapuram',
  'Government Engineering College, Palakkad',
  'Government Engineering College, Kozhikode',
  'Government Engineering College, Kannur',
  'Government Engineering College, Idukki',
  'Government Engineering College, Wayanad',
  'TKM College of Engineering, Kollam',
  'Sree Chitra Thirunal College of Engineering, Thiruvananthapuram',
  'Mar Athanasius College of Engineering, Kothamangalam',
  'Rajagiri School of Engineering & Technology, Kochi',
  'Model Engineering College, Thrikkakara',
  'Adi Shankara Institute of Engineering and Technology, Kalady',
  'Federal Institute of Science and Technology (FISAT), Angamaly',
  'Muthoot Institute of Technology and Science (MITS), Varapuzha',
  'SCMS School of Engineering and Technology, Karukutty',
  'Saintgits College of Engineering, Kottayam',
  'Mangalam College of Engineering, Ettumanoor',
  'Sree Narayana Gurukulam College of Engineering, Kolenchery',
  'Jyothi Engineering College, Cheruthuruthy',
  'Vidya Academy of Science and Technology, Thrissur',
  'Amrita Vishwa Vidyapeetham, Amritapuri',
  'Cochin University of Science and Technology (CUSAT)',
  'Government Polytechnic College, Palakkad',
  'Government Polytechnic College, Thrissur',
  'Government Polytechnic College, Kothamangalam',
  'Government Polytechnic College, Kozhikode',
  'Government Polytechnic College, Kannur',
  "Women's Polytechnic College, Thiruvananthapuram",
  'Sree Narayana Polytechnic College, Kottiyam',
  'Carmel Polytechnic College, Alappuzha',
  'NSS Polytechnic College, Pandalam',
];

export const BRANCH_SUGGESTIONS = [
  'Computer Science and Engineering',
  'Computer Science and Engineering (AI & ML)',
  'Artificial Intelligence and Data Science',
  'Information Technology',
  'Electronics and Communication Engineering',
  'Electrical and Electronics Engineering',
  'Mechanical Engineering',
  'Civil Engineering',
  'Chemical Engineering',
  'Instrumentation and Control Engineering',
  'Robotics and Automation',
  'Automobile Engineering',
  'Aerospace Engineering',
  'Biotechnology',
  'Biomedical Engineering',
  'Food Technology',
  'Production Engineering',
  'Safety and Fire Engineering',
  'Naval Architecture and Ship Building',
  'Computer Engineering (Diploma)',
  'Mechanical Engineering (Diploma)',
  'Civil Engineering (Diploma)',
  'Electrical and Electronics Engineering (Diploma)',
  'Electronics Engineering (Diploma)',
  'Automobile Engineering (Diploma)',
];

export const YEAR_SUGGESTIONS = [
  '1st Year',
  '2nd Year',
  '3rd Year',
  '4th Year',
  '5th Year',
  '6th Year',
];

export const INDIAN_STATES = [
  'Kerala',
  'Tamil Nadu',
  'Karnataka',
  'Andhra Pradesh',
  'Telangana',
  'Maharashtra',
  'Delhi',
  'Goa',
  'Gujarat',
  'Rajasthan',
  'Uttar Pradesh',
  'West Bengal',
  'Madhya Pradesh',
  'Bihar',
  'Odisha',
  'Punjab',
  'Haryana',
  'Jharkhand',
  'Chhattisgarh',
  'Assam',
  'Himachal Pradesh',
  'Uttarakhand',
  'Jammu and Kashmir',
  'Puducherry',
  'Chandigarh',
  'Tripura',
  'Meghalaya',
  'Manipur',
  'Nagaland',
  'Mizoram',
  'Arunachal Pradesh',
  'Sikkim',
  'Ladakh',
  'Andaman and Nicobar Islands',
  'Lakshadweep',
  'Dadra and Nagar Haveli and Daman and Diu',
];

export const KERALA_CITIES = [
  'Palakkad',
  'Thrissur',
  'Thiruvananthapuram',
  'Kochi',
  'Kozhikode',
  'Malappuram',
  'Kannur',
  'Kollam',
  'Alappuzha',
  'Kottayam',
  'Pathanamthitta',
  'Idukki',
  'Wayanad',
  'Kasaragod',
  'Ernakulam',
  'Ottapalam',
  'Shoranur',
  'Pattambi',
  'Mannarkkad',
  'Chalakudy',
  'Irinjalakuda',
  'Kunnamkulam',
  'Guruvayur',
  'Aluva',
  'Angamaly',
  'Kothamangalam',
  'Muvattupuzha',
  'Perinthalmanna',
  'Manjeri',
  'Tirur',
  'Ponnani',
  'Nilambur',
  'Thalassery',
  'Payyanur',
  'Vatakara',
  'Kanhangad',
  'Kalpetta',
  'Sulthan Bathery',
  'Thodupuzha',
  'Pala',
  'Changanassery',
  'Cherthala',
  'Kayamkulam',
  'Adoor',
  'Karunagappally',
  'Punalur',
  'Nedumangad',
  'Attingal',
  'Neyyattinkara',
];

export function normalizeYear(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  if (/^[1-6]$/.test(raw)) return YEAR_SUGGESTIONS[Number(raw) - 1];
  return raw;
}

export function parseYearNumber(value) {
  const match = String(value ?? '').match(/[1-6]/);
  return match ? Number(match[0]) : null;
}

export function ComboInput({
  value,
  onChange,
  options,
  placeholder,
  required = false,
  disabled = false,
  maxLength,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const query = String(value || '').trim().toLowerCase();
  const filtered = query
    ? options.filter((opt) => opt.toLowerCase().includes(query))
    : options;

  useEffect(() => {
    const onDocDown = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

  return (
    <div className="combo-field" ref={wrapRef}>
      <input
        type="text"
        value={value}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
        }}
        placeholder={placeholder}
        autoComplete="off"
        required={required}
        disabled={disabled}
        maxLength={maxLength}
      />
      {open && !disabled && filtered.length > 0 ? (
        <div
          className="combo-menu"
          role="listbox"
          data-lenis-prevent
          onWheel={(e) => e.stopPropagation()}
        >
          {filtered.map((opt) => (
            <button
              key={opt}
              type="button"
              className={`combo-option${opt === value ? ' is-active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(opt);
                setOpen(false);
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function SelectInput({ value, onChange, options, placeholder, disabled = false }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const selected = options.find((opt) => opt.value === value);

  useEffect(() => {
    const onDocDown = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

  return (
    <div className="combo-field" ref={wrapRef}>
      <button
        type="button"
        className={`combo-select-btn${selected ? '' : ' is-placeholder'}`}
        onClick={() => !disabled && setOpen((v) => !v)}
        disabled={disabled}
        aria-expanded={open}
      >
        <span>{selected ? selected.label : placeholder}</span>
        <ChevronDown size={15} strokeWidth={2} className={`combo-chevron${open ? ' is-open' : ''}`} />
      </button>
      {open && !disabled ? (
        <div
          className="combo-menu"
          role="listbox"
          data-lenis-prevent
          onWheel={(e) => e.stopPropagation()}
        >
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`combo-option${opt.value === value ? ' is-active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

